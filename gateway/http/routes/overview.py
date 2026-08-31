"""The Painel's overview: five KPIs, each with a decomposition and a daily series.

One document rather than five endpoints, because the Painel renders the five
together and five round trips would be five chances for the tile grid to
render half a page while the rest is still loading.

Every value here is read from a source that already exists — `EstateRepository
.summarise`, the estate's own daily snapshot, `/v1/incidents` and `/v1/runs`'
own listings — never a second opinion of a number one of those already
answers, and never a day invented for the sparkline that day has no reading
for.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from statistics import median as _median
from typing import Final

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from config.constants.observation import MAX_INCIDENT_PAGE_SIZE
from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.config_service.service import ConfigService
from platform.incidents.service import DetectorService
from platform.persistence.ports.estate_snapshot_store import EstateDailySnapshot
from platform.persistence.ports.incident_store import Incident, IncidentQuery
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus

router = APIRouter(tags=["overview"])

#: Mirrors `console/src/design/status.ts`'s own `SETTLED_RUN_STATUSES`: a run
#: whose process is gone will not change again, whether it reached a
#: conclusion or not. No shared Python vocabulary module exists yet for run
#: status the way `design/status.ts` is one for the console — see this
#: feature's control file for the gap this local mirror stands in for.
_SETTLED_RUN_STATUSES: Final = frozenset(
    {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.INTERRUPTED}
)


class SeriesPointView(BaseModel):
    """One daily bucket of a KPI's sparkline."""

    date: str
    value: float


class KpiView(BaseModel):
    """One KPI: its current value, a decomposition, and a daily trend.

    `value` is `None` — never a fabricated zero — when nothing in the window
    can answer the question, which for a rate is "no terminal item yet".
    """

    value: float | None = None
    breakdown: dict[str, float] = Field(default_factory=dict)
    series: list[SeriesPointView] = Field(default_factory=list)
    #: Set only when there is something to say beyond numbers — the KPI of
    #: degraded resources, when no detector is promoting anything to an
    #: incident. Empty otherwise.
    note: str = ""


class OverviewView(BaseModel):
    """The five KPI tiles the Painel renders, from one read."""

    captured_at: datetime
    watched: KpiView
    degraded: KpiView
    self_resolved: KpiView
    success_rate: KpiView
    time_to_cause: KpiView


def _window(now: datetime) -> tuple[date, date, datetime]:
    """Return `(since, until, window_start)` for the overview's trailing window."""
    until = now.date()
    since = until - timedelta(days=MAX_OVERVIEW_DAILY_BUCKETS - 1)
    window_start = datetime.combine(since, datetime.min.time(), tzinfo=UTC)
    return since, until, window_start


def _watched(
    summary_total: int,
    summary_by_kind: dict[str, int],
    daily: tuple[EstateDailySnapshot, ...],
) -> KpiView:
    """Return the "resources watched" KPI, from the estate summary and its history."""
    return KpiView(
        value=float(summary_total),
        breakdown={kind: float(count) for kind, count in summary_by_kind.items()},
        series=[
            SeriesPointView(date=snapshot.snapshot_date.isoformat(), value=float(snapshot.total))
            for snapshot in daily
        ],
    )


def _degraded(
    problems: int,
    daily: tuple[EstateDailySnapshot, ...],
    *,
    any_detector_enabled: bool,
) -> KpiView:
    """Return the "degraded now" KPI, and say when nothing promotes a finding.

    The daily series sums the two problem health states straight off each
    day's own snapshot — the same two `EstateSummary.problems` counts, read
    back from history rather than recomputed by a different rule.
    """
    series = [
        SeriesPointView(
            date=snapshot.snapshot_date.isoformat(),
            value=float(
                snapshot.counts_by_health.get("degraded", 0)
                + snapshot.counts_by_health.get("unhealthy", 0)
            ),
        )
        for snapshot in daily
    ]
    return KpiView(
        value=float(problems),
        note="" if any_detector_enabled else "no_detector_enabled",
        series=series,
    )


def _self_resolved(incidents: tuple[Incident, ...], *, since: date, until: date) -> KpiView:
    """Return the "closed on its own" KPI, over incidents opened in the window."""
    terminal = [
        incident
        for incident in incidents
        if incident.state.is_closed and since <= incident.opened_at.date() <= until
    ]
    unattended = [incident for incident in terminal if incident.self_resolved]
    if not terminal:
        return KpiView(value=None, breakdown={"self_resolved": 0.0, "total": 0.0})

    by_day: dict[date, list[Incident]] = {}
    for incident in terminal:
        by_day.setdefault(incident.opened_at.date(), []).append(incident)
    series = [
        SeriesPointView(
            date=day.isoformat(),
            value=round(100 * sum(1 for entry in entries if entry.self_resolved) / len(entries), 1),
        )
        for day, entries in sorted(by_day.items())
    ]
    return KpiView(
        value=round(100 * len(unattended) / len(terminal), 1),
        breakdown={"self_resolved": float(len(unattended)), "total": float(len(terminal))},
        series=series,
    )


def _success_rate(runs: tuple[AgentRun, ...], *, since: date, until: date) -> KpiView:
    """Return the "investigations that concluded cleanly" KPI."""
    settled = [
        run
        for run in runs
        if run.status in _SETTLED_RUN_STATUSES
        and run.started_at is not None
        and since <= run.started_at.date() <= until
    ]
    succeeded = [run for run in settled if run.status is RunStatus.COMPLETED]
    if not settled:
        return KpiView(value=None, breakdown={"succeeded": 0.0, "total": 0.0})

    by_day: dict[date, list[AgentRun]] = {}
    for run in settled:
        assert run.started_at is not None  # narrowed by the filter above
        by_day.setdefault(run.started_at.date(), []).append(run)
    series = [
        SeriesPointView(
            date=day.isoformat(),
            value=round(
                100
                * sum(1 for entry in entries if entry.status is RunStatus.COMPLETED)
                / len(entries),
                1,
            ),
        )
        for day, entries in sorted(by_day.items())
    ]
    return KpiView(
        value=round(100 * len(succeeded) / len(settled), 1),
        breakdown={"succeeded": float(len(succeeded)), "total": float(len(settled))},
        series=series,
    )


def _duration_seconds(run: AgentRun) -> float | None:
    if run.started_at is None or run.finished_at is None:
        return None
    seconds = (run.finished_at - run.started_at).total_seconds()
    return seconds if seconds > 0 else None


def _time_to_cause(runs: tuple[AgentRun, ...], *, since: date, until: date) -> KpiView:
    """Return the "how long to an answer" KPI: the median, and the worst case.

    The median rather than the mean, for the reason the console's own current
    computation already gives: one run that hit its wall clock must not drag a
    figure this exists to describe the ordinary case with.
    """
    durations: list[tuple[date, float]] = []
    for run in runs:
        if run.started_at is None or not (since <= run.started_at.date() <= until):
            continue
        seconds = _duration_seconds(run)
        if seconds is not None:
            durations.append((run.started_at.date(), seconds))

    if not durations:
        return KpiView(value=None, breakdown={"median_seconds": 0.0, "worst_seconds": 0.0})

    all_seconds = sorted(seconds for _, seconds in durations)
    worst = all_seconds[-1]
    measured = _median(all_seconds)

    by_day: dict[date, list[float]] = {}
    for day, seconds in durations:
        by_day.setdefault(day, []).append(seconds)
    series = [
        SeriesPointView(date=day.isoformat(), value=round(_median(sorted(values)), 1))
        for day, values in sorted(by_day.items())
    ]
    return KpiView(
        value=round(measured, 1),
        breakdown={"median_seconds": round(measured, 1), "worst_seconds": round(worst, 1)},
        series=series,
    )


async def _detector_service(state: GatewayState, auth: AuthenticatedRequest) -> DetectorService:
    """Return the detector service over this scope's resolved configuration.

    The same composition `gateway/http/routes/incidents.py::_detectors` uses,
    repeated here rather than imported from it: that helper is private to its
    own module, and the alternative — promoting it to a shared location — is
    named in this feature's control file as a small refactor for whoever
    touches this next, not one this feature makes on a route it does not own.
    """
    node_id = auth.team_node_id or auth.scope.org_id
    effective = await ConfigService(gateway=state.gateway, scope=auth.scope).resolve(node_id)
    return DetectorService(gateway=state.gateway, settings=effective.config.policies.observation)


@router.get("/v1/overview", response_model=OverviewView)
async def overview(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> OverviewView:
    """Return the five KPI tiles the Painel renders, from one read."""
    now = datetime.now(UTC)
    since, until, window_start = _window(now)

    async with state.gateway.begin(auth.scope) as uow:
        summary = await uow.estate.summarise(now=now)
        daily = await uow.estate_snapshots.list_daily(since=since, until=until)
        incidents = await uow.incidents.query(
            IncidentQuery(opened_after=window_start, limit=MAX_INCIDENT_PAGE_SIZE)
        )
        runs = await uow.run_traces.list_runs(since=window_start, limit=MAX_QUERY_PAGE_SIZE)

    detectors = await _detector_service(state, auth)
    detector_views = await detectors.list(auth.scope, now=now)
    any_enabled = any(view.declaration.enabled for view in detector_views)

    return OverviewView(
        captured_at=now,
        watched=_watched(summary.total, dict(summary.by_kind), daily),
        degraded=_degraded(summary.problems, daily, any_detector_enabled=any_enabled),
        self_resolved=_self_resolved(incidents, since=since, until=until),
        success_rate=_success_rate(runs, since=since, until=until),
        time_to_cause=_time_to_cause(runs, since=since, until=until),
    )


__all__ = ["router"]
