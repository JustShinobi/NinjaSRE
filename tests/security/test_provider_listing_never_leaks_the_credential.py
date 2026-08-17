"""The provider listing never puts the credential where a person could read it.

Two places a secret could escape from this route: the response body, and any
log line the request produces. Both are swept the same way
``test_credential_write_never_leaks.py`` sweeps the credential-write route —
by searching for the value itself, not for a shape.

The credential travels to a listing implementation as a
:class:`ProviderCredentials`, the same type every other caller in
``core.llm`` resolves it through, and this sweep proves what happens once one
is handed a real value: an implementation that failed and echoed the key it
just used in its own exception text must not have that text reach an
external field either.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from core.llm.catalogue import ListingUnavailable, ModelOffering, register_catalogue
from gateway.http.app import create_app
from gateway.http.routes.providers import reset_catalogue_cache
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.security

#: Distinctive enough that a substring search cannot match it by accident.
SENTINEL_API_KEY = "AIzaSy-sentinel-0f1e2d3c4b5a69788796a5b4c3d2e1f0"


@pytest.fixture(autouse=True)
def _no_cached_listing_between_tests() -> Iterator[None]:
    """Every test in this file registers its own catalogue for the same
    provider — a process-wide cache surviving between them would answer from
    whichever test ran first, which is the opposite of what a sweep needs."""
    reset_catalogue_cache()
    yield
    reset_catalogue_cache()


@pytest.fixture
def captured_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture everything every logger emits, at every level."""
    with caplog.at_level(logging.NOTSET):
        yield caplog


@pytest.fixture
async def wired() -> AsyncIterator[tuple[AsyncClient, str, GatewayState]]:
    """Return the real application, a real operator token, and its state."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS, kind=ConfigNodeKind.TEAM, name=TEAM_PAYMENTS, parent_id=ORG
            )
        )
    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    secret = await issue_token(
        gateway, tokens, user_id="ada", role=Role.OPERATOR, node_id=TEAM_PAYMENTS
    )
    transport = ASGITransport(app=create_app(state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http, secret, state


def _log_text(caplog: pytest.LogCaptureFixture) -> str:
    parts: list[str] = [caplog.text]
    for record in caplog.records:
        parts.append(str(record.getMessage()))
        parts.append(repr(getattr(record, "__dict__", {})))
    return "\n".join(parts)


class _CapturingCatalogue:
    """Records the credential it was handed, and answers normally.

    Proves the sweep below is not vacuously true because nothing ever saw the
    credential: ``seen_keys`` shows the real value reached the implementation.
    """

    def __init__(self) -> None:
        self.seen_keys: list[str] = []

    async def list_models(self, credentials: object) -> tuple[ModelOffering, ...]:
        key = getattr(credentials, "get", lambda *_: None)("api_key")
        if key:
            self.seen_keys.append(key)
        return (ModelOffering("gemini-pro-latest", "Gemini Pro"),)


class _BrokenCatalogue:
    """Fails, and echoes the credential it just used — a vendor SDK's own habit."""

    async def list_models(self, credentials: object) -> tuple[ModelOffering, ...]:
        key = getattr(credentials, "get", lambda *_: None)("api_key")
        raise ListingUnavailable(f"the endpoint rejected the request signed with {key}")


async def test_the_listing_response_never_carries_the_credential(
    wired: tuple[AsyncClient, str, GatewayState],
    monkeypatch: pytest.MonkeyPatch,
    captured_logs: pytest.LogCaptureFixture,
) -> None:
    http, secret, _state = wired
    monkeypatch.setenv("GOOGLE_API_KEY", SENTINEL_API_KEY)
    catalogue = _CapturingCatalogue()
    register_catalogue("google_gemini", catalogue)

    response = await http.get(
        "/v1/providers/google_gemini/models",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    assert SENTINEL_API_KEY in catalogue.seen_keys

    body_text = response.text
    assert SENTINEL_API_KEY not in body_text
    assert "model_id" in json.loads(body_text)["models"][0]
    assert SENTINEL_API_KEY not in _log_text(captured_logs)


async def test_a_listing_failure_does_not_quote_the_credential_in_its_refusal(
    wired: tuple[AsyncClient, str, GatewayState],
    monkeypatch: pytest.MonkeyPatch,
    captured_logs: pytest.LogCaptureFixture,
) -> None:
    http, secret, _state = wired
    monkeypatch.setenv("GOOGLE_API_KEY", SENTINEL_API_KEY)
    register_catalogue("google_gemini", _BrokenCatalogue())

    response = await http.get(
        "/v1/providers/google_gemini/models",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    body = response.json()
    # A refusal is still served — falls back to the static list, labelled —
    # never a 500 that could carry a traceback of its own.
    assert body["source"] == "static"
    assert SENTINEL_API_KEY not in response.text
    assert SENTINEL_API_KEY not in _log_text(captured_logs)


async def test_an_unhandled_verifier_failure_is_logged_with_the_credential_redacted(
    wired: tuple[AsyncClient, str, GatewayState],
    captured_logs: pytest.LogCaptureFixture,
) -> None:
    """A composed verifier that raises rather than returning a verdict is
    exactly the shape a real credential-proxy integration could fail in. The
    ASGI test transport re-raises past this app's own middleware rather than
    handing back the sanitised response a real deployment's server would —
    a property of ``BaseHTTPMiddleware`` under a test client, not of this
    feature — so what is provable here is what actually reached a log line,
    which is where the redaction this test is about actually happens.
    """
    http, secret, state = wired

    async def broken_verifier(provider_id: str, model_id: str | None = None) -> None:
        del provider_id, model_id
        raise RuntimeError(f"provider rejected api_key={SENTINEL_API_KEY!r}")

    state.model_verifier = broken_verifier  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        await http.post(
            "/v1/providers/google_gemini/verify",
            headers={"Authorization": f"Bearer {secret}"},
        )

    logged = _log_text(captured_logs)
    assert "gateway.unhandled_exception" in logged
    assert SENTINEL_API_KEY not in logged
    assert "[REDACTED]" in logged
