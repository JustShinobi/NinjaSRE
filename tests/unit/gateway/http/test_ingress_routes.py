"""What an operator has to paste into the system that will send the alerts.

The whole feature turns on somebody doing one thing outside this deployment:
configuring a receiver in the alert router. Everything the platform can do about
that is say precisely what to paste — the URL, the credential, and the body it
will parse — and this is the read that says it.

The URL is taken from the address the request arrived on rather than from
configuration. An operator reading this page reached the deployment somehow, and
that is the address that works; a configured one is a second copy of a fact that
is right until somebody moves the deployment.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from gateway.webhooks.router import PROFILES
from platform.identity.permissions import Permission, Role
from tests.unit.gateway.http.conftest import Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def test_every_configured_source_is_described(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Seven receivers exist; a panel listing six is a receiver nobody can find."""
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ops", role=Role.OPERATOR, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    sources = response.json()["sources"]
    assert {entry["source"] for entry in sources} == set(PROFILES)


async def test_each_source_says_where_to_post_and_what_to_post(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A path alone is not something anybody can paste."""
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ops", role=Role.OPERATOR, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    entry = next(row for row in response.json()["sources"] if row["source"] == "alertmanager")
    assert entry["path"] == "/webhooks/alertmanager"
    assert entry["url"].endswith("/webhooks/alertmanager")
    assert entry["url"].startswith("http")
    assert "groupKey" in entry["expects"]
    assert entry["verification"]


async def test_it_names_the_permission_a_delivery_token_needs(
    client: AsyncClient, deployment: Deployment
) -> None:
    """So the panel issues the narrow credential rather than a personal one."""
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ops", role=Role.OPERATOR, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["delivery_permission"] == Permission.WEBHOOK_DELIVER.value


async def test_it_carries_no_field_a_credential_could_sit_in(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A read of "how do I connect this" must never become a read of a credential.

    Asserted against the shape rather than by scanning the text: the prose
    genuinely says the words "shared secret" and "machine token", because that
    is what an operator has to know, and a test that searched for them would
    fail on the documentation being right.
    """
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ops", role=Role.OPERATOR, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert set(body) == {"sources", "delivery_permission"}
    for entry in body["sources"]:
        assert set(entry) == {"source", "path", "url", "expects", "verification"}


async def test_a_viewer_may_not_read_it(client: AsyncClient, deployment: Deployment) -> None:
    """Connecting a source is an operator's act, and this is its first step."""
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="looker", role=Role.VIEWER, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403, response.text
