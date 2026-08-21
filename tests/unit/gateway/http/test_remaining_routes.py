"""Smoke coverage for the routes not already covered by their own contract test:
schedules CRUD, memory, capabilities, integrations, health, and interactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from core.agent.interaction.models import Question
from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _auth_header(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_health_is_public_and_reports_readiness(client: AsyncClient) -> None:
    live = await client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["live"] is True

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True


async def test_schedule_lifecycle(client: AsyncClient, deployment: Deployment) -> None:
    headers = await _auth_header(deployment)
    created = await client.post(
        "/v1/schedules",
        json={
            "job_id": "nightly",
            "name": "Nightly sweep",
            "cron": "0 3 * * *",
            "objective": "sweep the fleet",
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["next_run_at"] is not None

    listed = await client.get("/v1/schedules", headers=headers)
    assert any(item["job_id"] == "nightly" for item in listed.json())

    disabled = await client.post("/v1/schedules/nightly/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    deleted = await client.delete("/v1/schedules/nightly", headers=headers)
    assert deleted.status_code == 204

    gone = await client.get("/v1/schedules/nightly", headers=headers)
    assert gone.status_code == 404


async def test_an_invalid_cron_expression_is_rejected(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.post(
        "/v1/schedules",
        json={"job_id": "bad", "name": "bad", "cron": "not a cron expression", "objective": "x"},
        headers=headers,
    )
    assert response.status_code == 400


async def test_schedule_preview_shows_the_next_firings_without_storing_anything(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.post(
        "/v1/schedules/preview",
        json={"cron": "0 8 * * 1", "timezone": "UTC"},
        headers=headers,
    )
    assert response.status_code == 200
    firings = response.json()["firings"]
    assert len(firings) == 2

    first = datetime.fromisoformat(firings[0]["at"])
    second = datetime.fromisoformat(firings[1]["at"])
    assert first < second
    # "0 8 * * 1" is Monday at 08:00 and nothing else — the field positions the
    # form's own helper text describes, not a guess about which Monday.
    for at in (first, second):
        assert at.weekday() == 0
        assert (at.hour, at.minute) == (8, 0)
    assert second - first == timedelta(days=7)

    # Nothing was stored: a preview of a job id nobody created must not appear
    # in the listing.
    listed = await client.get("/v1/schedules", headers=headers)
    assert listed.json() == []


async def test_schedule_preview_of_a_refused_cron_names_what_is_wrong(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.post(
        "/v1/schedules/preview",
        json={"cron": "99 7 * * 1", "timezone": "UTC"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "minute field" in response.json()["error"]["message"]


async def test_schedule_preview_needs_a_credential_like_every_other_schedule_route(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/v1/schedules/preview", json={"cron": "0 8 * * 1", "timezone": "UTC"}
    )
    assert response.status_code == 400


async def test_memory_search_and_stats(client: AsyncClient, deployment: Deployment) -> None:
    headers = await _auth_header(deployment)
    stats = await client.get("/v1/memory/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["episode_count"] == 0

    search = await client.get("/v1/memory/search", headers=headers)
    assert search.status_code == 200
    assert search.json()["episodes"] == []


async def test_capabilities_catalogue_is_readable(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.get("/v1/capabilities", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json()["tools"], list)


async def test_integrations_list(client: AsyncClient, deployment: Deployment) -> None:
    headers = await _auth_header(deployment)
    response = await client.get("/v1/integrations", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json()["integrations"], list)


async def test_answering_a_pending_question(client: AsyncClient, deployment: Deployment) -> None:
    headers = await _auth_header(deployment)
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    run_id = created.json()["run_id"]

    question = Question(
        interaction_id="q-1",
        run_id=run_id,
        raised_at=datetime.now(UTC),
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        text="Did the deploy finish?",
    )
    deployment.runner.interactions["q-1"] = question

    pending = await client.get(f"/v1/investigations/{run_id}/interactions", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()["interactions"]) == 1

    answered = await client.post(
        "/v1/interactions/q-1/answer", json={"text": "yes"}, headers=headers
    )
    assert answered.status_code == 200
    assert answered.json()["is_open"] is False


async def test_answering_an_unknown_interaction_is_404(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.post(
        "/v1/interactions/does-not-exist/answer", json={"text": "yes"}, headers=headers
    )
    assert response.status_code == 404
