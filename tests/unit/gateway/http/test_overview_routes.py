"""`GET /v1/overview` over HTTP: the five KPIs, and the two things a client must not do.

A client must not recompute a figure the route already served — so this test
checks the tiles are actually present in one document, with a decomposition
and a series each — and the route must not exist for anybody who has not
requested it, which the route table (`tests/security/test_route_permissions
.py`) is what proves the permission is enforced, not this file.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from platform.persistence.ports.estate_repository import HealthDerivation, Resource, ResourceHealth
from platform.persistence.ports.estate_snapshot_store import EstateDailySnapshot
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio


def _now() -> datetime:
    return datetime.now(UTC)


async def _headers(deployment: Deployment) -> dict[str, str]:
    from platform.identity.permissions import Role

    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="u-owner", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _seed_estate(deployment: Deployment, *, now: datetime) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-a",
                kind="container",
                source="proxmox",
                native_id="ct/1",
                display_name="ct-1",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await uow.estate.record_health(
            "res-a",
            HealthDerivation(state=ResourceHealth.HEALTHY, rule="provider_status", derived_at=now),
        )


async def test_the_overview_serves_all_five_kpis_with_a_decomposition_and_a_series(
    client: AsyncClient, deployment: Deployment
) -> None:
    now = _now()
    await _seed_estate(deployment, now=now)

    response = await client.get("/v1/overview", headers=await _headers(deployment))

    assert response.status_code == 200, response.text
    body = response.json()
    for name in ("watched", "degraded", "self_resolved", "success_rate", "time_to_cause"):
        assert name in body, f"the overview must serve a {name!r} tile"
        assert "breakdown" in body[name]
        assert "series" in body[name]


async def test_watched_is_the_estates_own_summary_never_a_second_count(
    client: AsyncClient, deployment: Deployment
) -> None:
    now = _now()
    await _seed_estate(deployment, now=now)

    response = await client.get("/v1/overview", headers=await _headers(deployment))

    body = response.json()
    assert body["watched"]["value"] == 1
    assert body["watched"]["breakdown"].get("container") == 1


async def test_degraded_says_when_nothing_promotes_a_finding_to_an_incident(
    client: AsyncClient, deployment: Deployment
) -> None:
    # Nothing configures a detector for this org, so nothing promotes a
    # finding — the honest state FR-021 asks the KPI to say outright.
    response = await client.get("/v1/overview", headers=await _headers(deployment))

    body = response.json()
    assert body["degraded"]["note"] == "no_detector_enabled"


async def test_a_kpi_with_nothing_in_the_window_reads_as_unmeasured_not_zero(
    client: AsyncClient, deployment: Deployment
) -> None:
    # No incidents and no runs exist for this organisation at all, so a rate
    # computed over zero terminal items must say "not measured" rather than
    # invent a 0% — the same honesty rule the estate KPIs get for a failed read.
    response = await client.get("/v1/overview", headers=await _headers(deployment))

    body = response.json()
    assert body["self_resolved"]["value"] is None
    assert body["success_rate"]["value"] is None
    assert body["time_to_cause"]["value"] is None


async def test_the_daily_series_never_exceeds_the_declared_bucket_bound(
    client: AsyncClient, deployment: Deployment
) -> None:
    now = _now()
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for offset in range(MAX_OVERVIEW_DAILY_BUCKETS + 5):
            day = now.date().fromordinal(now.date().toordinal() - offset)
            await uow.estate_snapshots.record(
                EstateDailySnapshot(snapshot_date=day, total=offset, captured_at=now)
            )

    response = await client.get("/v1/overview", headers=await _headers(deployment))

    body = response.json()
    assert len(body["watched"]["series"]) <= MAX_OVERVIEW_DAILY_BUCKETS
