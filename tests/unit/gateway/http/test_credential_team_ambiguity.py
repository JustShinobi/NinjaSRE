"""Two teams holding the same integration's credential is a real shape, told plainly.

The process does not choose one of the two in silence: the binding and the
provider lease both fall back to the organisation-wide handle
(``gateway.http.credential_handles``), and this is the other half — the
catalogue an operator actually reads has to say that the choice was made, and
for which vendor, or "which credential does an investigation use" has no
answer a person can find.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.credential_schemas import schema_for
from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    TEAM_PLATFORM,
    Deployment,
    issue_token,
)

pytestmark = pytest.mark.unit

INTEGRATION = "grafana"
ORG_SCOPE = TenantScope(org_id=ORG)


def _value_for(field_name: str) -> str:
    """Return a value that satisfies the field's own shape, not just its presence."""
    return "https://grafana.internal.example" if field_name == "endpoint" else "does-not-matter"


async def _store(deployment: Deployment, *, team_id: str) -> None:
    vault = Vault(
        gateway=deployment.gateway,
        schemas=CredentialSchemaRegistry.from_schemas(schema_for(INTEGRATION)),
    )
    handle = CredentialHandle(integration=INTEGRATION, team_id=team_id)
    values = {
        field.name: _value_for(field.name)
        for field in schema_for(INTEGRATION).fields
        if field.required
    }
    await vault.store(ORG_SCOPE, handle, values)


@pytest.fixture
async def manager_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def client(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


async def _catalogue(http: AsyncClient, token: str) -> dict[str, Any]:
    response = await http.get("/v1/integrations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _row(body: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(entry for entry in body["integrations"] if entry["name"] == name)
    return found


async def test_one_team_holding_a_credential_is_not_reported_as_ambiguous(
    deployment: Deployment, client: AsyncClient, manager_token: str
) -> None:
    await _store(deployment, team_id=TEAM_PAYMENTS)

    body = await _catalogue(client, manager_token)

    assert (await _row(body, INTEGRATION))["credential_team_ambiguous"] is False


async def test_two_teams_holding_the_same_integration_is_reported_as_ambiguous(
    deployment: Deployment, client: AsyncClient, manager_token: str
) -> None:
    await _store(deployment, team_id=TEAM_PAYMENTS)
    await _store(deployment, team_id=TEAM_PLATFORM)

    body = await _catalogue(client, manager_token)

    assert (await _row(body, INTEGRATION))["credential_team_ambiguous"] is True


async def test_the_ambiguity_does_not_leak_onto_an_unrelated_integration(
    deployment: Deployment, client: AsyncClient, manager_token: str
) -> None:
    await _store(deployment, team_id=TEAM_PAYMENTS)
    await _store(deployment, team_id=TEAM_PLATFORM)

    body = await _catalogue(client, manager_token)

    others = [entry for entry in body["integrations"] if entry["name"] != INTEGRATION]
    assert others
    assert all(entry["credential_team_ambiguous"] is False for entry in others)
