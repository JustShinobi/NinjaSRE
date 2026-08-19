"""Disconnecting an integration: the DELETE beside the credential write.

The console's "Disconnect" offers this and nothing else — it is not a second
form, it is the same vault entry the write puts a value into, taken back out.
Everything asserted here mirrors what ``test_onboarding_routes.py`` already
holds for the write: the same permission gate, the same 404 for a name nothing
answers to, and a response with nowhere a secret could sit — there is nothing
here to leak in the first place, since a delete carries no value in either
direction, but the shape is checked anyway so a future field cannot smuggle
one in unnoticed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.identity.audit.recorder import CREDENTIAL_AUDIT_ACTION_DELETE
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

CREDENTIAL_PATH = "/v1/integrations/redis/credential"
SENTINEL_API_KEY = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
SENTINEL_SECRET_KEY = "abcdefghij0123456789ABCDEFGHIJ0123456789"


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
async def operator_token(deployment: Deployment) -> str:
    """A token holding ``credential.write``, at the team the handle is scoped to."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def viewer_token(deployment: Deployment) -> str:
    """A token holding none of the write permissions."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="viv",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )


async def _store(client: AsyncClient, token: str) -> None:
    response = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(token),
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
    )
    assert response.status_code == 200


# --- Disconnecting removes what was stored -------------------------------------


async def test_disconnecting_removes_every_version_from_the_vault(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    await _store(client, operator_token)
    rotated = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": "rotated-key", "secret_key": SENTINEL_SECRET_KEY}},
    )
    assert rotated.status_code == 200

    response = await client.delete(CREDENTIAL_PATH, headers=_headers(operator_token))

    assert response.status_code == 200
    body = response.json()
    assert body["integration"] == "redis"
    # Two versions were written above (the store, then a rotation); both go.
    assert body["versions_removed"] == 2

    vault = Vault(gateway=deployment.gateway, schemas=CredentialSchemaRegistry())
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    live = await vault.active(scope, CredentialHandle(integration="redis", team_id=TEAM_PAYMENTS))
    assert live is None


async def test_disconnecting_something_never_configured_removes_nothing_and_still_succeeds(
    client: AsyncClient, operator_token: str
) -> None:
    """Idempotent, not refused: a stale panel pressed twice meets no error."""
    response = await client.delete(CREDENTIAL_PATH, headers=_headers(operator_token))

    assert response.status_code == 200
    assert response.json()["versions_removed"] == 0


async def test_the_response_carries_nothing_a_value_could_sit_in(
    client: AsyncClient, operator_token: str
) -> None:
    await _store(client, operator_token)

    response = await client.delete(CREDENTIAL_PATH, headers=_headers(operator_token))

    assert SENTINEL_API_KEY not in response.text
    assert SENTINEL_SECRET_KEY not in response.text
    assert set(response.json().keys()) == {"integration", "versions_removed"}


# --- What it refuses ------------------------------------------------------------


async def test_an_unknown_integration_is_not_found(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.delete(
        "/v1/integrations/no-such-vendor/credential", headers=_headers(operator_token)
    )

    assert response.status_code == 404


async def test_a_caller_without_credential_write_is_refused(
    client: AsyncClient, viewer_token: str
) -> None:
    response = await client.delete(CREDENTIAL_PATH, headers=_headers(viewer_token))

    assert response.status_code == 403


# --- The record it leaves --------------------------------------------------------


async def test_disconnecting_is_recorded_in_the_audit_trail_as_its_own_action(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    await _store(client, operator_token)

    await client.delete(CREDENTIAL_PATH, headers=_headers(operator_token))

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    written = [
        event
        for event in events
        if event.action == CREDENTIAL_AUDIT_ACTION_DELETE and event.resource_id == "redis"
    ]
    assert len(written) == 1
    assert written[0].actor_id == "ada"
    assert written[0].outcome.value == "allowed"
    assert written[0].detail["versions_removed"] == 1
    # Never the action a write leaves — a delete wearing the write's own
    # action name is indistinguishable from a write in the trail somebody
    # reads six months later.
    assert not any(
        event.action != CREDENTIAL_AUDIT_ACTION_DELETE
        and event.resource_id == "redis"
        and event.detail.get("versions_removed") == 1
        for event in events
    )
