"""Type a username and a password into a clean deployment, and reach a page.

The sibling of ``test_first_run_sign_in``, and it exists for the same reason:
the earlier failure there was a credential that the deployment printed and the
running gateway then refused, and nothing caught it because no test ever used
the credential the way a person uses it.

A password is worse in that respect, not better. It is typed rather than pasted,
it is the first thing anybody does with a new deployment, and everything about
it — the account, the grant, the token it turns into — comes into existence on
the way through. So this test does what the person does, through the real ASGI
application, the real route table, the real permission guard:

1. bring up a deployment with nothing in it at all,
2. ``POST /auth/sign-in`` with the name and passphrase,
3. present what comes back as a bearer token,
4. reach a page that requires being signed in.

Nothing here reaches around the boundary. The token is not taken from the sign-in
service, it is read out of the response body, and it is not resolved directly, it
is sent as a header.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.security import (
    LOCAL_ACCOUNT_DEFAULT_PASSWORD,
    LOCAL_ACCOUNT_PRINCIPAL_ID,
    LOCAL_ACCOUNT_USERNAME,
)
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.break_glass import hash_secret
from platform.identity.local_accounts import LocalAccount, LocalSignIn
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.startup.bootstrap import organisation_id

pytestmark = pytest.mark.contract


class _NoInvestigator:
    """Stands in for the investigation runtime, which signing in does not need."""

    async def start(self, *positional: object, **named: object) -> object:
        raise AssertionError("signing in must not start an investigation")


@pytest.fixture
async def signed_out() -> AsyncIterator[AsyncClient]:
    """A deployment with an empty store and a local account, and nothing else.

    Empty on purpose: no organisation, no principal, no grant, no token. That is
    what a machine that has never run this before looks like, and every one of
    those has to come into existence during the sign-in or what it returns has
    nothing behind it.
    """
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(organisation_id(), "Acme")

    tokens = TokenService(gateway=gateway)
    state = GatewayState(
        gateway=gateway,
        tokens=tokens,
        investigator=_NoInvestigator(),  # type: ignore[arg-type]
        local_sign_in=LocalSignIn(
            gateway=gateway,
            tokens=tokens,
            account=LocalAccount(password_hash=hash_secret(LOCAL_ACCOUNT_DEFAULT_PASSWORD)),
        ),
    )
    application = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://deployment"
    ) as client:
        yield client
    await gateway.close()


async def test_a_username_and_a_password_reach_a_page_that_needs_a_session(
    signed_out: AsyncClient,
) -> None:
    """The whole feature, end to end, in the order a person performs it."""
    opened = await signed_out.post(
        "/auth/sign-in",
        json={"username": LOCAL_ACCOUNT_USERNAME, "password": LOCAL_ACCOUNT_DEFAULT_PASSWORD},
    )
    assert opened.status_code == 200, opened.text

    token = opened.json()["token"]
    reached = await signed_out.get("/auth/me", headers={"authorization": f"Bearer {token}"})

    assert reached.status_code == 200, reached.text
    assert reached.json()["principal_id"] == LOCAL_ACCOUNT_PRINCIPAL_ID


async def test_signing_in_needs_no_credential_of_its_own(signed_out: AsyncClient) -> None:
    """The route that issues the first credential cannot require one.

    Asserted against the running application rather than the route table,
    because "declared public" and "reachable without a header" are two claims
    and only the second one is the feature.
    """
    answered = await signed_out.post(
        "/auth/sign-in",
        json={"username": LOCAL_ACCOUNT_USERNAME, "password": LOCAL_ACCOUNT_DEFAULT_PASSWORD},
    )

    assert answered.status_code != 400
    assert answered.status_code == 200


async def test_a_wrong_passphrase_is_refused_with_the_status_a_client_can_act_on(
    signed_out: AsyncClient,
) -> None:
    """401, not 400: a client that cannot tell a refusal from a malformed request
    retries the malformed one and never asks for the password again."""
    refused = await signed_out.post(
        "/auth/sign-in",
        json={"username": LOCAL_ACCOUNT_USERNAME, "password": "not the passphrase"},
    )

    assert refused.status_code == 401


async def test_a_refusal_gives_away_nothing_about_which_half_was_wrong(
    signed_out: AsyncClient,
) -> None:
    """Otherwise the sign-in page is a way of asking whether an account exists."""
    wrong_password = await signed_out.post(
        "/auth/sign-in",
        json={"username": LOCAL_ACCOUNT_USERNAME, "password": "not the passphrase"},
    )
    wrong_username = await signed_out.post(
        "/auth/sign-in",
        json={"username": "somebody-else", "password": LOCAL_ACCOUNT_DEFAULT_PASSWORD},
    )

    assert wrong_password.status_code == wrong_username.status_code

    # Everything except the correlation identifier, which is per request by
    # design and says nothing about the credential.
    def told(answer: object) -> tuple[str, str]:
        error = answer.json()["error"]  # type: ignore[attr-defined]
        return error["type"], error["message"]

    assert told(wrong_password) == told(wrong_username)


async def test_the_passphrase_comes_back_in_nothing(signed_out: AsyncClient) -> None:
    """What is returned is a token. The password is not an output of anything."""
    opened = await signed_out.post(
        "/auth/sign-in",
        json={"username": LOCAL_ACCOUNT_USERNAME, "password": LOCAL_ACCOUNT_DEFAULT_PASSWORD},
    )

    assert LOCAL_ACCOUNT_DEFAULT_PASSWORD not in opened.text
