"""Where a self-hosted integration's address goes when an operator types it.

Written at the organisation's node rather than the caller's team: the binding
that makes the vendor call is organisation-wide, so a team-node address would be
read by nothing — a form that accepted a value and changed no behaviour.

One form, two destinations. The secret goes to the vault, which has no read-back
and never will. The address goes to the configuration tree, which is where the
proxy already reads its egress allow-list from — so declaring where a vendor is
and permitting the deployment to reach it stay one act rather than two an
operator has to know to perform separately.

The failure this pins is the one the staging deployment actually had: a
credential stored, a green tick beside it, and every call still addressed to
``alertmanager.example.com`` because nothing had asked where the Alertmanager
was.
"""

from __future__ import annotations

from httpx import AsyncClient

from platform.config_service.service import ConfigService
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

ADDRESS = "http://10.20.20.36:9093"


async def _admin(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.ADMIN,
        node_id=TEAM_PAYMENTS,
    )
    return {"authorization": f"Bearer {secret}"}


async def test_the_catalogue_asks_where_a_self_hosted_vendor_is(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A form with no address field is one an operator can complete and not connect."""
    answer = await client.get("/v1/integrations", headers=await _admin(deployment))

    assert answer.status_code == 200
    entry = next(row for row in answer.json()["integrations"] if row["name"] == "alertmanager")
    address = next(field for field in entry["fields"] if field["name"] == "endpoint")
    assert address["secret"] is False
    assert address["required"] is True


async def test_the_address_reaches_the_configuration_the_proxy_reads(
    client: AsyncClient, deployment: Deployment
) -> None:
    written = await client.put(
        "/v1/integrations/alertmanager/credential",
        headers=await _admin(deployment),
        json={"values": {"endpoint": ADDRESS}},
    )

    assert written.status_code == 200, written.text

    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    config = ConfigService(gateway=deployment.gateway, scope=scope)
    effective = await config.resolve(ORG)
    entry = effective.config.integrations.for_name("alertmanager")
    assert entry is not None
    assert entry.base_url == ADDRESS
    assert entry.enabled is True


async def test_the_address_is_never_written_to_the_vault(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The vault holds credentials. An address is not one, and it is readable."""
    await client.put(
        "/v1/integrations/alertmanager/credential",
        headers=await _admin(deployment),
        json={"values": {"endpoint": ADDRESS, "token": "a-token-behind-a-proxy"}},
    )

    from integrations.alertmanager.schema import SCHEMA

    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    vault = Vault(gateway=deployment.gateway, schemas=CredentialSchemaRegistry.from_schemas(SCHEMA))
    stored = await vault.list(scope)
    assert [version.integration for version in stored] == ["alertmanager"]

    written = await client.put(
        "/v1/integrations/alertmanager/credential",
        headers=await _admin(deployment),
        json={"values": {"endpoint": ADDRESS}},
    )
    assert written.json()["fields"] == ["endpoint"]


async def test_an_alertmanager_with_no_auth_of_its_own_can_be_connected(
    client: AsyncClient, deployment: Deployment
) -> None:
    """It ships none. Requiring a token made the ordinary install unconnectable."""
    written = await client.put(
        "/v1/integrations/alertmanager/credential",
        headers=await _admin(deployment),
        json={"values": {"endpoint": ADDRESS}},
    )

    assert written.status_code == 200, written.text


async def test_an_address_that_is_not_one_is_refused_before_anything_is_stored(
    client: AsyncClient, deployment: Deployment
) -> None:
    written = await client.put(
        "/v1/integrations/alertmanager/credential",
        headers=await _admin(deployment),
        json={"values": {"endpoint": "10.20.20.36:9093"}},
    )

    assert written.status_code == 400
    assert "http://" in written.json()["error"]["message"]

    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    config = ConfigService(gateway=deployment.gateway, scope=scope)
    effective = await config.resolve(ORG)
    assert effective.config.integrations.for_name("alertmanager") is None


async def test_changing_the_address_replaces_it_rather_than_adding_a_second(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _admin(deployment)
    for address in (ADDRESS, "https://alertmanager.acme.example"):
        answer = await client.put(
            "/v1/integrations/alertmanager/credential",
            headers=headers,
            json={"values": {"endpoint": address}},
        )
        assert answer.status_code == 200, answer.text

    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    config = ConfigService(gateway=deployment.gateway, scope=scope)
    effective = await config.resolve(ORG)
    active = effective.config.integrations.active
    assert [entry.name for entry in active] == ["alertmanager"]
    assert active[0].base_url == "https://alertmanager.acme.example"
