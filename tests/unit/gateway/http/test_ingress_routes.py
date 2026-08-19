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


async def _admin(deployment: Deployment) -> dict[str, str]:
    """Return the header of a principal that may issue a machine token."""
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.ADMIN, node_id=None
    )
    return {"Authorization": f"Bearer {secret}"}


async def _issue_delivery_token(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    """Issue a real machine token scoped to delivery, and return its secret."""
    response = await client.post(
        "/identity/tokens",
        headers=headers,
        json={
            "name": name,
            "user_id": "ada",
            "permissions": [Permission.WEBHOOK_DELIVER.value],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["secret"])


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
        assert set(entry) == {
            "source",
            "path",
            "url",
            "expects",
            "verification",
            "receiver_yaml",
        }


async def test_a_viewer_may_not_read_it(client: AsyncClient, deployment: Deployment) -> None:
    """Connecting a source is an operator's act, and this is its first step."""
    token = await issue_token(
        deployment.gateway, deployment.tokens, user_id="looker", role=Role.VIEWER, node_id=None
    )
    response = await client.get("/v1/ingress/sources", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403, response.text


# --- The Alertmanager receiver block ------------------------------------------------


async def test_alertmanager_carries_a_receiver_yaml_once_a_delivery_token_exists(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The paste-ready block appears only once there is a token to name in it,
    and only on the one source it actually authenticates."""
    headers = await _admin(deployment)
    await _issue_delivery_token(client, headers, "Alert delivery")

    response = await client.get("/v1/ingress/sources", headers=headers)

    sources = {entry["source"]: entry for entry in response.json()["sources"]}
    assert sources["alertmanager"]["receiver_yaml"] is not None
    assert "Alert delivery" in sources["alertmanager"]["receiver_yaml"]
    assert sources["grafana"]["receiver_yaml"] is None
    assert sources["generic"]["receiver_yaml"] is None


async def test_the_receiver_yaml_carries_this_deployment_s_own_url(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _admin(deployment)
    await _issue_delivery_token(client, headers, "Alert delivery")

    response = await client.get("/v1/ingress/sources", headers=headers)

    sources = {entry["source"]: entry for entry in response.json()["sources"]}
    assert sources["alertmanager"]["url"] in sources["alertmanager"]["receiver_yaml"]


async def test_the_receiver_yaml_is_absent_without_any_delivery_token(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Without a token to name, there is nothing usable to copy — the field is
    absent rather than a block that would not authenticate."""
    headers = await _admin(deployment)

    response = await client.get("/v1/ingress/sources", headers=headers)

    sources = {entry["source"]: entry for entry in response.json()["sources"]}
    assert sources["alertmanager"]["receiver_yaml"] is None


async def test_the_receiver_yaml_names_the_most_recently_issued_delivery_token(
    client: AsyncClient, deployment: Deployment
) -> None:
    """More than one valid delivery token: the block names the one actually in
    use, not merely "a" token — the same reading the trust line on the intake
    screen already makes."""
    headers = await _admin(deployment)
    await _issue_delivery_token(client, headers, "old delivery token")
    await _issue_delivery_token(client, headers, "current delivery token")

    response = await client.get("/v1/ingress/sources", headers=headers)

    sources = {entry["source"]: entry for entry in response.json()["sources"]}
    assert "current delivery token" in sources["alertmanager"]["receiver_yaml"]
    assert "old delivery token" not in sources["alertmanager"]["receiver_yaml"]


async def test_the_receiver_yaml_never_carries_a_credential_s_own_value(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The secret this test just received from the issuance response must never
    reappear anywhere in a later, unrelated read."""
    headers = await _admin(deployment)
    secret = await _issue_delivery_token(client, headers, "Alert delivery")

    response = await client.get("/v1/ingress/sources", headers=headers)

    body = response.text
    assert secret not in body
