"""Creating, reading, listing, and cancelling investigations through the real HTTP surface."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _auth_header(
    deployment: Deployment, *, node_id: str | None = TEAM_PAYMENTS
) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=node_id
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_creating_an_investigation_returns_its_identity_immediately(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance scenario 1."""
    headers = await _auth_header(deployment)
    response = await client.post(
        "/v1/investigations", json={"objective": "checkout error rate is elevated"}, headers=headers
    )
    assert response.status_code == 202
    body = response.json()
    assert body["run_id"]
    assert body["status"] == "running"


async def test_a_request_with_no_token_is_refused() -> None:
    from httpx import ASGITransport

    from gateway.http.app import create_app
    from gateway.http.state import GatewayState
    from platform.identity.tokens import TokenService
    from platform.persistence.fakes import FakePersistence
    from tests.unit.gateway.http.conftest import FakeInvestigationRunner

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    state = GatewayState(
        gateway=gateway,
        tokens=TokenService(gateway=gateway),
        investigator=FakeInvestigationRunner(),
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        response = await http.post("/v1/investigations", json={"objective": "x"})
    assert response.status_code == 400


async def test_getting_an_unknown_investigation_is_404(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.get("/v1/investigations/does-not-exist", headers=headers)
    assert response.status_code == 404


async def test_created_investigation_is_visible_in_list_and_get(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    created = await client.post(
        "/v1/investigations", json={"objective": "pod crash-looping"}, headers=headers
    )
    run_id = created.json()["run_id"]

    listed = await client.get("/v1/investigations", headers=headers)
    assert any(item["run_id"] == run_id for item in listed.json()["investigations"])

    got = await client.get(f"/v1/investigations/{run_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["run_id"] == run_id


async def test_cancelling_an_investigation_asks_the_runner(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    run_id = created.json()["run_id"]

    response = await client.post(f"/v1/investigations/{run_id}/cancel", headers=headers)
    assert response.status_code == 200
    assert run_id in deployment.runner.cancelled


async def test_queueing_a_message_asks_the_runner(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    run_id = created.json()["run_id"]

    response = await client.post(
        f"/v1/investigations/{run_id}/messages",
        json={"text": "check the other pod too"},
        headers=headers,
    )
    assert response.status_code == 202
    assert (run_id, "check the other pod too") in deployment.runner.queued


async def test_taking_over_a_run_asks_the_runner_to_pause_at_its_next_safe_point(
    client: AsyncClient, deployment: Deployment
) -> None:
    """An operator takes control; the run suspends rather than ending.

    Distinct from cancelling in the state it leaves behind and in nothing else
    about how it stops: a taken-over run is resumable with its evidence intact,
    and a cancelled one is over.
    """
    headers = await _auth_header(deployment)
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    run_id = created.json()["run_id"]

    response = await client.post(f"/v1/investigations/{run_id}/take-over", headers=headers)

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert run_id in deployment.runner.taken_over
    assert run_id not in deployment.runner.cancelled


async def test_resuming_a_taken_over_run_hands_it_back(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    run_id = created.json()["run_id"]
    await client.post(f"/v1/investigations/{run_id}/take-over", headers=headers)

    response = await client.post(f"/v1/investigations/{run_id}/resume", headers=headers)

    assert response.status_code == 200
    assert run_id in deployment.runner.resumed


async def test_taking_over_a_run_of_another_team_is_not_found(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The same chain every other route on a run walks: run, team, caller."""
    headers = await _auth_header(deployment)
    response = await client.post("/v1/investigations/no-such-run/take-over", headers=headers)

    assert response.status_code == 404
