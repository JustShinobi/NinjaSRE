"""``GET /v1/integrations`` says whether a credential is stored, not only
whether a live check ever ran.

Before this file's fix every row that had not been through a live check read
``health: "unknown"`` whether or not anything had ever been written for it —
so a card for an integration nobody has touched and a card for one that is
connected and simply unverified were the same word. ``unconfigured`` is
computed from the same bulk vault read ``gateway/http/configured.py`` already
serves the estate with, joined here with the verification ledger the route
already reads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

CREDENTIAL_PATH = "/v1/integrations/datadog/credential"


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_an_integration_nobody_has_connected_reads_unconfigured(
    client: AsyncClient, manager_token: str
) -> None:
    response = await client.get("/v1/integrations", headers=_headers(manager_token))

    assert response.status_code == 200
    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["datadog"]["health"] == "unconfigured"


async def test_storing_a_credential_flips_it_to_unknown_not_healthy(
    client: AsyncClient, manager_token: str
) -> None:
    """Stored is not the same claim as verified — only a live check earns
    ``healthy``, so writing a credential must land on ``unknown``."""
    await client.put(
        CREDENTIAL_PATH,
        headers=_headers(manager_token),
        json={"values": {"api_key": "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "app_key": "x" * 40}},
    )

    response = await client.get("/v1/integrations", headers=_headers(manager_token))

    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["datadog"]["health"] == "unknown"


async def test_verifying_a_stored_credential_moves_it_to_healthy(
    client: AsyncClient, manager_token: str
) -> None:
    await client.put(
        CREDENTIAL_PATH,
        headers=_headers(manager_token),
        json={"values": {"api_key": "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "app_key": "x" * 40}},
    )

    await client.post("/v1/integrations/datadog/verify", headers=_headers(manager_token))
    response = await client.get("/v1/integrations", headers=_headers(manager_token))

    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["datadog"]["health"] == "healthy"
