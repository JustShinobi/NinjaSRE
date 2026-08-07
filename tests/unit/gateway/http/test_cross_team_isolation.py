"""SC-006: cross-team access is impossible through every route.

A token scoped to one team, asking about a run or a schedule that belongs to
another, gets exactly what a non-existent resource gets: 404. Never a 403 that
would confirm it exists, and never the record itself.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, TEAM_PLATFORM, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _token_for(deployment: Deployment, user_id: str, team: str) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id=user_id, role=Role.OWNER, node_id=team
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_a_team_cannot_read_another_teams_investigation(
    client: AsyncClient, deployment: Deployment
) -> None:
    payments = await _token_for(deployment, "ada", TEAM_PAYMENTS)
    platform = await _token_for(deployment, "bob", TEAM_PLATFORM)

    created = await client.post(
        "/v1/investigations", json={"objective": "checkout is down"}, headers=payments
    )
    run_id = created.json()["run_id"]

    cross_team = await client.get(f"/v1/investigations/{run_id}", headers=platform)
    assert cross_team.status_code == 404

    own_team = await client.get(f"/v1/investigations/{run_id}", headers=payments)
    assert own_team.status_code == 200


async def test_a_teams_investigation_list_excludes_other_teams(
    client: AsyncClient, deployment: Deployment
) -> None:
    payments = await _token_for(deployment, "ada", TEAM_PAYMENTS)
    platform = await _token_for(deployment, "bob", TEAM_PLATFORM)

    created = await client.post(
        "/v1/investigations", json={"objective": "payments incident"}, headers=payments
    )
    run_id = created.json()["run_id"]

    listed = await client.get("/v1/investigations", headers=platform)
    assert all(item["run_id"] != run_id for item in listed.json()["investigations"])


async def test_a_team_cannot_cancel_another_teams_investigation(
    client: AsyncClient, deployment: Deployment
) -> None:
    payments = await _token_for(deployment, "ada", TEAM_PAYMENTS)
    platform = await _token_for(deployment, "bob", TEAM_PLATFORM)

    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=payments)
    run_id = created.json()["run_id"]

    response = await client.post(f"/v1/investigations/{run_id}/cancel", headers=platform)
    assert response.status_code == 404
    assert run_id not in deployment.runner.cancelled


async def test_a_team_cannot_read_another_teams_config(
    client: AsyncClient, deployment: Deployment
) -> None:
    payments = await _token_for(deployment, "ada", TEAM_PAYMENTS)
    platform = await _token_for(deployment, "bob", TEAM_PLATFORM)

    denied = await client.get(f"/v1/config/{TEAM_PAYMENTS}", headers=platform)
    assert denied.status_code == 404

    allowed = await client.get(f"/v1/config/{TEAM_PAYMENTS}", headers=payments)
    assert allowed.status_code == 200


async def test_a_team_cannot_read_another_teams_schedule(
    client: AsyncClient, deployment: Deployment
) -> None:
    payments = await _token_for(deployment, "ada", TEAM_PAYMENTS)
    platform = await _token_for(deployment, "bob", TEAM_PLATFORM)

    created = await client.post(
        "/v1/schedules",
        json={
            "job_id": "nightly",
            "name": "Nightly sweep",
            "cron": "0 3 * * *",
            "objective": "sweep",
        },
        headers=payments,
    )
    assert created.status_code == 201

    cross_team = await client.get("/v1/schedules/nightly", headers=platform)
    assert cross_team.status_code == 404
