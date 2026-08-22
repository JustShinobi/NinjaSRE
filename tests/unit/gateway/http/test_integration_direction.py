"""Which way the traffic goes, said on the screen that asks for the credential.

The confusion this answers is a real one an operator hit: Alertmanager appears
in the catalogue asking for a token, and the token that makes alerts *arrive* is
a different secret, issued on a different screen, presented by the alert router
rather than by this deployment. Nothing said so. Two secrets shared one word and
the screen that asked for one never mentioned the other.

Direction is derived rather than declared. A vendor package cannot import the
gateway, and a `direction` field on fifteen profiles is fifteen chances to say
something the webhook router does not agree with. The router's own source list
is the fact; this reads it.
"""

from __future__ import annotations

from httpx import AsyncClient

from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token


async def _catalogue(client: AsyncClient, deployment: Deployment) -> dict[str, dict]:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.ADMIN,
        node_id=TEAM_PAYMENTS,
    )
    answer = await client.get("/v1/integrations", headers={"authorization": f"Bearer {secret}"})
    assert answer.status_code == 200, answer.text
    return {row["name"]: row for row in answer.json()["integrations"]}


async def test_a_vendor_this_deployment_only_reads_is_named_outbound(
    client: AsyncClient, deployment: Deployment
) -> None:
    rows = await _catalogue(client, deployment)

    assert rows["prometheus"]["direction"] == "outbound"
    assert rows["prometheus"]["intake_path"] == ""


async def test_a_vendor_that_also_delivers_here_says_so_and_names_where(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Alertmanager is both, and the second half is the one nobody was told about."""
    rows = await _catalogue(client, deployment)

    assert rows["alertmanager"]["direction"] == "both"
    assert rows["alertmanager"]["intake_path"] == "/webhooks/alertmanager"
    assert rows["grafana"]["direction"] == "both"


async def test_every_integration_states_a_direction(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A blank one would be a state the console has to invent a word for.

    Two answers and no third: a catalogued integration always has a client, so
    "inbound only" is a state this catalogue cannot hold.
    """
    rows = await _catalogue(client, deployment)

    assert rows
    for name, row in rows.items():
        assert row["direction"] in {"outbound", "both"}, name


async def test_the_direction_follows_the_router_rather_than_a_second_list(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Add a webhook source and the catalogue says so, with no vendor package edited."""
    from gateway.webhooks.router import PROFILES

    rows = await _catalogue(client, deployment)
    receiving = {name for name, row in rows.items() if row["direction"] == "both"}

    assert receiving == {name for name in PROFILES if name in rows}
