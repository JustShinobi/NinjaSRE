"""``GET /v1/runs`` answers a question about status without handing over the page.

The console's shell asks two things of the run list on every full render:
the recent runs, for the palette, and the runs that ended badly, for the
attention band. The second used to be answered by reading the whole recent
page and filtering it in the browser's server — fifty full runs, a fifth of a
megabyte, on every screen — so this is where the filter belongs: in the
query, as a repeatable ``status``, the way ``/v1/incidents`` already takes
``state``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from platform.persistence.ports import AgentRun, RunStatus, TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _seed(deployment: Deployment) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for run_id, status in (
            ("run-ok", RunStatus.COMPLETED),
            ("run-failed", RunStatus.FAILED),
            ("run-cancelled", RunStatus.CANCELLED),
            ("run-lost", RunStatus.INTERRUPTED),
        ):
            await uow.run_traces.start_run(AgentRun(run_id=run_id, trigger="alert"))
            await uow.run_traces.complete_run(
                run_id, status=status, finished_at=datetime(2026, 9, 1, tzinfo=UTC)
            )


async def _headers(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_the_listing_takes_several_statuses_and_returns_only_those(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    response = await client.get(
        "/v1/runs",
        params=[("status", "failed"), ("status", "cancelled"), ("status", "interrupted")],
        headers=await _headers(deployment),
    )

    assert response.status_code == 200
    assert {run["run_id"] for run in response.json()["runs"]} == {
        "run-failed",
        "run-cancelled",
        "run-lost",
    }


async def test_no_status_still_returns_the_whole_recent_page(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    response = await client.get("/v1/runs", headers=await _headers(deployment))

    assert response.status_code == 200
    assert len(response.json()["runs"]) == 4


async def test_a_status_this_deployment_has_no_word_for_is_refused_as_a_bad_request(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A 422, in the sanitised shape every validation refusal here takes."""
    await _seed(deployment)
    response = await client.get(
        "/v1/runs", params={"status": "exploded"}, headers=await _headers(deployment)
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "validation_error"


async def test_the_listing_takes_run_identifiers_and_returns_only_those(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    response = await client.get(
        "/v1/runs",
        params=[("run_id", "run-ok"), ("run_id", "run-lost"), ("run_id", "run-never")],
        headers=await _headers(deployment),
    )

    assert response.status_code == 200
    assert {run["run_id"] for run in response.json()["runs"]} == {"run-ok", "run-lost"}


async def test_identifiers_and_statuses_narrow_together(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    response = await client.get(
        "/v1/runs",
        params=[("run_id", "run-ok"), ("run_id", "run-failed"), ("status", "failed")],
        headers=await _headers(deployment),
    )

    assert response.status_code == 200
    assert [run["run_id"] for run in response.json()["runs"]] == ["run-failed"]
