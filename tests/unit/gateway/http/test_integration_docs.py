"""The package documentation route, read from the application FastAPI actually serves.

Not the router in isolation: ``gateway/http/app.py`` already mounts the
integrations router, and the property this suite proves is that the address
answers *there* — composed, authorised, and reading the real catalogue —
rather than only in a unit that imported the handler function directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio

REPO_ROOT = Path(__file__).resolve().parents[4]


async def _auth_header(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_an_embedded_vendors_documentation_is_the_text_of_its_own_docs_md(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)

    response = await client.get("/v1/integrations/alertmanager/docs", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "alertmanager"
    assert body["display_name"] == "Alertmanager"
    assert body["readable"] is True
    on_disk = (REPO_ROOT / "integrations" / "alertmanager" / "docs.md").read_text(encoding="utf-8")
    assert body["markdown"] == on_disk


async def test_a_name_that_is_not_an_installed_vendor_is_a_named_absence(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)

    response = await client.get("/v1/integrations/not-a-real-vendor-name/docs", headers=headers)

    assert response.status_code == 404
    assert "not-a-real-vendor-name" in response.json()["error"]["message"]


async def test_the_route_is_reached_without_a_bearer_token_being_accepted(
    client: AsyncClient,
) -> None:
    """No credential, no answer — the same rule every other route on this router holds."""
    response = await client.get("/v1/integrations/alertmanager/docs")

    assert response.status_code in (400, 401)


@pytest.mark.parametrize(
    "name",
    [
        "argocd",
        "github",
        "google_gemini",
        "grafana",
        "hermes",
        "kubernetes",
        "loki",
        "openobserve",
        "prometheus",
        "proxmox",
        "pushover",
        "redis",
        "signoz",
        "telegram",
    ],
)
async def test_every_other_embedded_vendors_documentation_is_also_served(
    client: AsyncClient, deployment: Deployment, name: str
) -> None:
    """Alertmanager is not special-cased: this route is generic over the catalogue."""
    headers = await _auth_header(deployment)

    response = await client.get(f"/v1/integrations/{name}/docs", headers=headers)

    assert response.status_code == 200
    assert response.json()["readable"] is True
    assert response.json()["markdown"] != ""
