"""`GET /v1/overview` over HTTP: the five KPIs, and the two things a client must not do.

A client must not recompute a figure the route already served — so this test
checks the tiles are actually present in one document, with a decomposition
and a series each — and the route must not exist for anybody who has not
requested it, which the route table (`tests/security/test_route_permissions
.py`) is what proves the permission is enforced, not this file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from config.constants.observation import MAX_INCIDENT_PAGE_SIZE
from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from platform.persistence.ports.estate_repository import HealthDerivation, Resource, ResourceHealth
from platform.persistence.ports.estate_snapshot_store import EstateDailySnapshot
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    incident_key,
    public_incident_id,
)
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

#: How far past one page the window-wide fixture reaches. Small enough that
#: seeding is quick, large enough that a first-page read and a whole-window
#: read cannot round to the same figure.
_BEYOND_ONE_PAGE = 30

#: The one run that took an hour rather than a minute. It sits among the
#: oldest, so it is only reachable once the read has drained the window.
_SLOWEST_RUN_SECONDS = 3600.0


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


async def _seed_more_than_one_page(deployment: Deployment, *, now: datetime) -> None:
    """Fill the window with more incidents and more runs than one page returns.

    The extras are the *oldest* items and they are the ones that differ: a
    read that stops at the first page sees only the newest, so every figure
    below has two possible answers and only one of them is the window's.
    """
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for index in range(MAX_INCIDENT_PAGE_SIZE + _BEYOND_ONE_PAGE):
            opened_at = now - timedelta(minutes=index + 5)
            internal_id = incident_key(f"detector:disk-{index}", opened_at)
            await uow.incidents.upsert(
                Incident(
                    incident_id=internal_id,
                    correlation_key=f"detector:disk-{index}",
                    title="Datastore near full",
                    summary="store-cove is 95.65% full",
                    origin=IncidentOrigin.DETECTOR,
                    origin_id="datastore-near-full",
                    severity="critical",
                    state=IncidentState.RESOLVED,
                    opened_at=opened_at,
                    subjects=(
                        IncidentSubject(
                            resource_id="store-cove",
                            detail="store-cove is 95.65% full",
                            evidence={"used_percent": "95.65"},
                            observed_at=opened_at,
                        ),
                    ),
                    closed_at=opened_at + timedelta(minutes=1),
                    self_resolved=index >= MAX_INCIDENT_PAGE_SIZE,
                    public_id=public_incident_id(internal_id),
                )
            )

        for index in range(MAX_QUERY_PAGE_SIZE + _BEYOND_ONE_PAGE):
            started_at = now - timedelta(minutes=index + 5)
            failed = index >= MAX_QUERY_PAGE_SIZE
            seconds = _SLOWEST_RUN_SECONDS if index == MAX_QUERY_PAGE_SIZE else 60.0
            await uow.run_traces.start_run(
                AgentRun(
                    run_id=f"run-{index:04d}",
                    trigger="alert",
                    status=RunStatus.FAILED if failed else RunStatus.COMPLETED,
                    started_at=started_at,
                    finished_at=started_at + timedelta(seconds=seconds),
                )
            )


async def test_the_kpis_are_computed_over_the_whole_window_not_its_first_page(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A tile says "N de M": M has to be the window, not the page that was read.

    Both listings behind these KPIs are capped at one page and both come back
    newest first, so an organisation with more than a page of activity in the
    window would otherwise read its busiest fortnight as exactly one page of
    it — a total the deployment never measured, presented as one it did.
    """
    now = _now()
    await _seed_more_than_one_page(deployment, now=now)
    incidents = MAX_INCIDENT_PAGE_SIZE + _BEYOND_ONE_PAGE
    runs = MAX_QUERY_PAGE_SIZE + _BEYOND_ONE_PAGE

    response = await client.get("/v1/overview", headers=await _headers(deployment))

    body = response.json()
    assert body["self_resolved"]["breakdown"]["total"] == incidents
    assert body["self_resolved"]["breakdown"]["self_resolved"] == _BEYOND_ONE_PAGE
    assert body["self_resolved"]["value"] == round(100 * _BEYOND_ONE_PAGE / incidents, 1)
    assert body["success_rate"]["breakdown"]["total"] == runs
    assert body["success_rate"]["breakdown"]["succeeded"] == MAX_QUERY_PAGE_SIZE
    assert body["success_rate"]["value"] == round(100 * MAX_QUERY_PAGE_SIZE / runs, 1)
    # The slowest run is one of the oldest, so a first-page read reports the
    # ordinary minute as the worst case the fortnight held.
    assert body["time_to_cause"]["breakdown"]["worst_seconds"] == _SLOWEST_RUN_SECONDS


async def test_the_overview_is_served_as_computed_for_a_short_window(
    client: AsyncClient, deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dashboard is the first screen of every session, and its figures are a fortnight's.

    Computing them drains every incident and run in the window on every
    render. Served as computed for ``OVERVIEW_CACHE_TTL_SECONDS``, with the
    ``captured_at`` the view already carries saying which instant the figures
    describe; forgetting them is what a test — or a deploy — does to see a
    fresh set.
    """
    from gateway.http.routes import overview as overview_route

    headers = await _headers(deployment)
    overview_route.forget_overviews(deployment.state)
    first = await client.get("/v1/overview", headers=headers)
    assert first.status_code == 200

    opened = {"units": 0}
    real_begin = deployment.gateway.begin

    def counted(scope):  # type: ignore[no-untyped-def]
        opened["units"] += 1
        return real_begin(scope)

    monkeypatch.setattr(deployment.gateway, "begin", counted)
    second = await client.get("/v1/overview", headers=headers)

    assert second.json()["captured_at"] == first.json()["captured_at"]
    assert opened["units"] == 0, "the remembered overview was recomputed"

    overview_route.forget_overviews(deployment.state)
    third = await client.get("/v1/overview", headers=headers)
    assert third.json()["captured_at"] != first.json()["captured_at"]
