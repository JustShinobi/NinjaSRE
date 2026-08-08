"""Bring up a clean deployment, take what the operator is given, and sign in.

This is the whole point of the feature and the reason it exists. A live run
brought the stack up, served fifty-one endpoints, rendered a sign-in — and the
administrator token the deployment printed into its environment was rejected by
the running gateway. A platform nobody can enter is, from where the operator is
standing, indistinguishable from one that does not work, and the reason nobody
noticed is that no test ever took the printed credential and used it.

So this test does exactly what the operator does, in the same order and from the
same places:

1. bring up a deployment with nothing in it,
2. read the credential from the file the operator is told to read,
3. present it to the running application as a bearer token,
4. reach a page that requires being signed in.

Nothing here reaches around the boundary. The token is not read out of the token
service, it is read off the disk; it is not resolved through ``TokenService``
directly, it is sent through the real ASGI application, the real permission
guard, and the real authorisation chain. Any test that read the token from
somewhere other than where the operator reads it would not have caught the
original failure.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.first_run import (
    BOOTSTRAP_CREDENTIAL_FILENAME,
    NINJASRE_STATE_DIR_ENV,
)
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.startup.bootstrap import bring_up

pytestmark = pytest.mark.contract


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the deployment's host state at a directory this test owns."""
    directory = tmp_path / "state"
    monkeypatch.setenv(NINJASRE_STATE_DIR_ENV, str(directory))
    yield directory


@pytest.fixture
async def clean_deployment() -> AsyncIterator[tuple[FakePersistence, TokenService, GatewayState]]:
    """Return a deployment with an empty store, wired the way the container wires it.

    Empty on purpose: no organisation, no principal, no grant, no token. That is
    what ``docker compose up`` meets on a machine that has never run this before,
    and every one of those has to come into existence during bring-up or the
    credential it prints has nothing behind it.
    """
    gateway = FakePersistence()
    tokens = TokenService(gateway=gateway)
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=_NoInvestigator())
    yield gateway, tokens, state
    await gateway.close()


class _NoInvestigator:
    """Stands in for the investigation runtime, which bring-up does not need.

    Signing in does not run an investigation, and composing a runtime needs a
    provider and the credential proxy. Everything this test asserts about is
    real; this is the one collaborator that is not, and it is not on the path.
    """

    async def investigate(self, request: object) -> str:  # pragma: no cover - never called
        raise AssertionError("signing in must not start an investigation")


async def _bring_up_and_read(
    gateway: FakePersistence, tokens: TokenService, state_dir: Path
) -> dict[str, object]:
    """Bring the deployment up and return the credential file's contents."""
    await bring_up(gateway, tokens)
    path = state_dir / BOOTSTRAP_CREDENTIAL_FILENAME
    assert path.exists(), (
        f"bring-up left no credential at {path}. This is the original failure: the "
        f"deployment came up and gave the operator nothing that signs in."
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


async def test_the_credential_bring_up_prints_signs_in_and_reaches_an_authenticated_page(
    clean_deployment: tuple[FakePersistence, TokenService, GatewayState], state_dir: Path
) -> None:
    """SC-001. Bring up, read the credential, sign in, reach a page behind the door."""
    gateway, tokens, state = clean_deployment
    document = await _bring_up_and_read(gateway, tokens, state_dir)

    secret = document["secret"]
    assert isinstance(secret, str) and secret, "the credential file carries no secret"

    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        response = await http.get("/auth/me", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 200, (
        f"the credential bring-up produced was rejected by the running gateway: "
        f"{response.status_code} {response.text}"
    )
    body = response.json()
    assert body["principal_id"], "the signed-in principal has no identity"
    assert body["permissions"], "the signed-in principal may do nothing at all"


async def test_the_credential_is_printed_with_an_expiry_the_operator_can_read(
    clean_deployment: tuple[FakePersistence, TokenService, GatewayState], state_dir: Path
) -> None:
    """FR-002. An expiry, in the file, in a form a person and a program both read."""
    gateway, tokens, state = clean_deployment
    document = await _bring_up_and_read(gateway, tokens, state_dir)

    expires_at = document["expires_at"]
    assert isinstance(expires_at, str)
    parsed = datetime.fromisoformat(expires_at)
    assert parsed.tzinfo is not None, "an expiry without a timezone is an expiry in whose day?"
    assert parsed > datetime.now(UTC), "bring-up printed a credential that had already expired"


async def test_the_credential_is_retrievable_again_without_restarting_anything(
    clean_deployment: tuple[FakePersistence, TokenService, GatewayState], state_dir: Path
) -> None:
    """FR-002. The operator who closed the terminal has not lost their deployment."""
    gateway, tokens, state = clean_deployment
    first = await _bring_up_and_read(gateway, tokens, state_dir)

    # Nothing is restarted, nothing is re-issued: the file is simply read again,
    # which is what an operator does when the scrollback is gone.
    again = json.loads(
        (state_dir / BOOTSTRAP_CREDENTIAL_FILENAME).read_text(encoding="utf-8"),
    )
    assert again["secret"] == first["secret"]

    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        response = await http.get(
            "/auth/me", headers={"Authorization": f"Bearer {again['secret']}"}
        )
    assert response.status_code == 200


async def test_the_credential_file_is_readable_only_by_its_owner(
    clean_deployment: tuple[FakePersistence, TokenService, GatewayState], state_dir: Path
) -> None:
    """A live credential on a shared host is not world-readable."""
    gateway, tokens, _ = clean_deployment
    await _bring_up_and_read(gateway, tokens, state_dir)

    mode = (state_dir / BOOTSTRAP_CREDENTIAL_FILENAME).stat().st_mode & 0o777
    assert mode == 0o600, f"the credential file is mode {mode:o}"
