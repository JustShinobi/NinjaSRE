"""What is wrong, what is being watched for, and the two things a person does about it.

Seven routes over two services. Two shapes are worth explaining, because both
are decisions rather than conveniences.

**An incident carries its subjects, never a count.** A response that said "50
affected" and nothing else would make correlation unfalsifiable: an operator who
suspected the grouping was too broad would have nothing to check it against. The
list is bounded by the incident's own subject bound, not by this route.

**A detector's verdict is computed at read time.** Nothing stores an
observation, so "what did this detector last conclude" is answered by evaluating
it against the signals that are already there. That is cheaper than a table of
every verdict and more honest than one: it is what the detector concludes now,
rather than what it concluded whenever something last wrote a row.

Closing takes a reason and refuses without one at the schema, before a handler
runs. "Closed by Ada" does not say whether it was fixed or dismissed, and a
deployment that recorded both the same way could not find the dismissals again.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from config.constants.observation import MAX_INCIDENT_PAGE_SIZE
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.config_service.service import ConfigService
from platform.incidents.errors import UnknownIncident
from platform.incidents.investigation_summary import InvestigationSummary, summarise_investigation
from platform.incidents.service import DetectorService, DetectorView, IncidentService
from platform.observation.detectors.conditions import Observation
from platform.observation.errors import UnknownDetector
from platform.persistence.errors import BoundExceeded
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentQuery,
    IncidentState,
    TimelineEntry,
)

router = APIRouter(prefix="/v1", tags=["incidents"])

#: How many incidents a listing returns when the caller does not say. A screen's
#: worth: an operator opening the list wants what is wrong now, not the year.
DEFAULT_INCIDENT_PAGE = 50


class SubjectView(BaseModel):
    """One resource an incident is about, and what was seen on it."""

    resource_id: str
    detail: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime | None = None
    absent_since: datetime | None = None


class IncidentSummaryView(BaseModel):
    """One incident as a table row shows it."""

    incident_id: str
    #: The short, URL-safe address this incident is reached by. What every
    #: link and every address bar carries; ``incident_id`` stays on the
    #: payload because the timeline references it and an operator debugging
    #: from the database needs it, but the console never emits it as a link.
    public_id: str
    title: str
    summary: str
    state: str
    severity: str
    origin: str
    #: What two firings of one cause share: the condition and the resource it
    #: fired on, which is what the store opens an incident *for* rather than
    #: opening a second one. It is mandatory on the domain object and used to
    #: be dropped here, and dropping it is what made a repeating estate
    #: unreadable — a client has nothing else to fold fifty firings of seven
    #: conditions back into seven rows with, because a title is prose and a
    #: subject list is not the cause. The console's own search already filters
    #: on this field and was matching the empty string.
    correlation_key: str
    #: The detector, the alert source, or the person who opened it.
    detector: str
    #: Every subject, named. Never a count — see the module docstring.
    subjects: list[str] = Field(default_factory=list)
    opened_at: datetime
    closed_at: datetime | None = None
    run_id: str | None = None
    team_node_id: str = ""
    self_resolved: bool = False
    suppressed_by: str = ""
    close_reason: str = ""


class IncidentListView(BaseModel):
    incidents: list[IncidentSummaryView]
    #: Whether detection is paused, and why. On the listing rather than a route
    #: of its own, because "why is this empty" is asked here.
    paused: bool = False
    pause_reason: str = ""


class TimelineEntryView(BaseModel):
    at: datetime
    kind: str
    actor: str
    cause: str = ""
    detail: str = ""
    #: The query an evidence step actually ran. Empty on every other kind —
    #: see ``TimelineEntry.query`` on the port this mirrors.
    query: str = ""
    #: What ``query`` returned. Carried beside it, not folded into a sentence,
    #: so the screen can render what was actually asked and what came back.
    result: str = ""


class ObservationView(BaseModel):
    """One thing a detector concluded about one resource."""

    detector: str
    subject: str
    verdict: str
    detail: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime


class InvestigationSummaryView(BaseModel):
    """How many steps the investigation took, how long it ran, and what it cost.

    ``duration_ms`` and ``cost`` are ``None`` — never a fabricated zero — while
    the run has not finished, or while nothing it did carried a priced figure.
    ``step_count`` gets no such treatment: a run that has taken no turns yet
    has taken zero turns, which is a fact worth showing exactly as it is.
    """

    step_count: int
    duration_ms: int | None = None
    cost: float | None = None
    #: The run's own status, in the product's vocabulary. Here because a screen
    #: that has to infer "still going" from what a timeline is missing gets it
    #: wrong the moment a run finishes without delivering anywhere — which it
    #: did, and drew "investigation running" beside "resolved" on one header.
    status: str = ""


class IncidentDetailView(BaseModel):
    """One incident's page: what it is, who it is about, and how it got there."""

    incident: IncidentSummaryView
    subjects: list[SubjectView] = Field(default_factory=list)
    observations: list[ObservationView] = Field(default_factory=list)
    timeline: list[TimelineEntryView] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    #: ``None`` only when no run was ever attached to this incident. An
    #: attached run always summarises to something, even before it has
    #: produced a single turn.
    investigation: InvestigationSummaryView | None = None


class DetectorSummaryView(BaseModel):
    """One detector as a table row shows it."""

    detector_id: str
    name: str
    description: str
    severity: str
    enabled: bool
    signal: str
    subjects_covered: int
    subjects_total: int
    last_verdict: str
    last_evaluated_at: datetime | None = None
    #: The document that proposed this detector, when one did. Empty for every
    #: detector somebody wrote by hand, and what lets a client separate "this is
    #: running" from "somebody's runbook suggests this and nobody has decided".
    origin: str = ""
    origin_excerpt: str = ""
    #: ``origin`` is set. Served rather than left to the client to derive, so
    #: two surfaces cannot disagree about what makes a row a candidate.
    proposed: bool = False


class DetectorListView(BaseModel):
    detectors: list[DetectorSummaryView]
    paused: bool = False
    pause_reason: str = ""


class ObservationListView(BaseModel):
    observations: list[ObservationView]


class DryRunView(BaseModel):
    """What a detector would have concluded, and the fact that it did nothing."""

    detector_id: str
    would_fire: bool
    observations: list[ObservationView] = Field(default_factory=list)
    #: Stated in the payload rather than implied by the route name, because the
    #: one thing an operator needs to be sure of before testing a threshold
    #: against last week is that it cannot page anybody.
    fired: bool = False


class CloseRequest(BaseModel):
    """Why an incident is being closed. Required, and refused at the schema.

    "Closed by Ada" does not say whether it was fixed or dismissed, and a
    deployment that recorded both the same way could not find the dismissals
    again — which is the search somebody runs when a detector turns out to have
    been wrong all along.
    """

    reason: str = Field(min_length=1)
    #: Which terminal state. Defaults to closed-without-action, which is the
    #: honest reading of a person closing something nobody acted on.
    resolved: bool = False


class SuppressRequest(BaseModel):
    """What covered this incident, and why."""

    rule: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def _incidents(state: GatewayState) -> IncidentService:
    return IncidentService(gateway=state.gateway)


def _config(state: GatewayState, auth: AuthenticatedRequest) -> ConfigService:
    """Return a configuration service for this request.

    Detector writes go through it rather than round it, so the audit line, the
    field locks, and the approval gate all still apply. A toggle that wrote
    around the configuration service would be an operator's decision with no
    record of who made it.
    """
    return ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)


async def _detectors(state: GatewayState, auth: AuthenticatedRequest) -> DetectorService:
    """Return the detector service over this scope's resolved configuration.

    Resolved on every call. A detector an operator added thirty seconds ago has
    to be in the next listing, and a cache invalidated by whatever wrote the
    configuration would be a cache with two owners.
    """
    node_id = auth.team_node_id or auth.scope.org_id
    effective = await _config(state, auth).resolve(node_id)
    return DetectorService(gateway=state.gateway, settings=effective.config.policies.observation)


def _row(incident: Incident) -> IncidentSummaryView:
    return IncidentSummaryView(
        incident_id=incident.incident_id,
        public_id=incident.public_id,
        title=incident.title,
        summary=incident.summary,
        state=incident.state.value,
        severity=incident.severity,
        origin=incident.origin.value,
        correlation_key=incident.correlation_key,
        detector=incident.origin_id,
        subjects=list(incident.subject_ids),
        opened_at=incident.opened_at,
        closed_at=incident.closed_at,
        run_id=incident.run_ids[0] if incident.run_ids else None,
        team_node_id=incident.team_node_id,
        self_resolved=incident.self_resolved,
        suppressed_by=incident.suppressed_by,
        close_reason=incident.close_reason,
    )


def _entry(entry: TimelineEntry) -> TimelineEntryView:
    return TimelineEntryView(
        at=entry.at,
        kind=entry.kind.value,
        actor=entry.actor,
        cause=entry.cause,
        detail=entry.detail,
        query=entry.query,
        result=entry.result,
    )


async def _investigation(
    state: GatewayState, auth: AuthenticatedRequest, run_ids: tuple[str, ...]
) -> InvestigationSummaryView | None:
    """Return this incident's investigation summary, or ``None`` if none was ever attached.

    An incident with no run attached has nothing to summarise, and says so with
    ``None`` rather than a summary of zeroes. Once a run *is* attached, this
    always returns something — even before that run has produced a single
    turn, and even in the moment right after attaching, before its own trace
    row exists yet — because the incident's own timeline already says an
    investigation started. Only the two numbers a run can genuinely lack,
    duration and cost, are ever omitted; the step count is a real count,
    zero included.
    """
    if not run_ids:
        return None
    run_id = run_ids[0]
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        turns = await uow.run_traces.turns_for_run(run_id) if run is not None else ()
    summary = (
        summarise_investigation(run, turns)
        if run is not None
        else InvestigationSummary(step_count=0)
    )
    return InvestigationSummaryView(
        step_count=summary.step_count,
        status=run.status.value if run is not None else "",
        duration_ms=(
            round(summary.duration_seconds * 1000) if summary.duration_seconds is not None else None
        ),
        cost=summary.cost_usd,
    )


def _observation(observation: Observation) -> ObservationView:
    return ObservationView(
        detector=observation.detector_id,
        subject=observation.resource_id,
        verdict=observation.verdict.value,
        detail=observation.detail,
        evidence=dict(observation.evidence),
        observed_at=observation.observed_at,
    )


def _detector(view: DetectorView) -> DetectorSummaryView:
    declaration = view.declaration
    return DetectorSummaryView(
        detector_id=declaration.detector_id,
        name=declaration.name,
        description=declaration.description,
        severity=declaration.severity.value,
        enabled=declaration.enabled,
        signal=declaration.signal,
        subjects_covered=view.subjects_covered,
        subjects_total=view.subjects_total,
        last_verdict=view.last_verdict,
        last_evaluated_at=view.last_evaluated_at,
        origin=declaration.origin,
        origin_excerpt=declaration.origin_excerpt,
        proposed=declaration.proposed,
    )


def _states(values: list[str]) -> tuple[IncidentState, ...]:
    """Return the requested states, refusing one outside the closed set.

    Refusing rather than ignoring. A client asking for ``state=acknowledged``
    and receiving every incident would conclude that every incident was
    acknowledged.
    """
    states: list[IncidentState] = []
    for value in values:
        try:
            states.append(IncidentState(value))
        except ValueError as unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"{value!r} is not an incident state. Expected one of: "
                    f"{', '.join(entry.value for entry in IncidentState)}."
                ),
            ) from unknown
    return tuple(states)


@router.get("/incidents", response_model=IncidentListView)
async def list_incidents(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    incident_state: list[str] = Query(default=[], alias="state"),
    severity: list[str] = Query(default=[]),
    detector: list[str] = Query(default=[]),
    subject: str = "",
    live: bool = False,
    limit: int = DEFAULT_INCIDENT_PAGE,
) -> IncidentListView:
    """Return the incidents matching every filter given, most recent first."""
    query = IncidentQuery(
        states=_states(incident_state),
        severities=tuple(severity),
        detector_ids=tuple(detector),
        subject_id=subject,
        live_only=live,
        limit=limit,
    )
    try:
        found = await _incidents(state).list(auth.scope, query)
    except BoundExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"a limit of {limit} exceeds the incident page bound of "
                f"{MAX_INCIDENT_PAGE_SIZE}. Page through them rather than asking for all."
            ),
        ) from exceeded

    detectors = await _detectors(state, auth)
    return IncidentListView(
        incidents=[_row(incident) for incident in found],
        paused=detectors.paused,
        pause_reason=detectors.pause_reason,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetailView)
async def incident_detail(
    incident_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IncidentDetailView:
    """Return one incident, its subjects, and how it got where it is."""
    detail = await _incidents(state).detail(auth.scope, incident_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident {incident_id!r} in this organisation",
        )
    return IncidentDetailView(
        incident=_row(detail.incident),
        subjects=[
            SubjectView(
                resource_id=subject.resource_id,
                detail=subject.detail,
                evidence=dict(subject.evidence),
                observed_at=subject.observed_at,
                absent_since=subject.absent_since,
            )
            for subject in detail.incident.subjects
        ],
        timeline=[_entry(entry) for entry in detail.timeline],
        actions=list(detail.incident.actions),
        investigation=await _investigation(state, auth, detail.incident.run_ids),
    )


@router.post("/incidents/{incident_id}/close", response_model=IncidentSummaryView)
async def close_incident(
    incident_id: str,
    request: CloseRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IncidentSummaryView:
    """Close an incident on a person's behalf, with their reason."""
    try:
        closed = await _incidents(state).close(
            auth.scope,
            incident_id,
            reason=request.reason,
            actor=auth.principal_id,
            state=(
                IncidentState.RESOLVED if request.resolved else IncidentState.CLOSED_WITHOUT_ACTION
            ),
            now=datetime.now(UTC),
        )
    except UnknownIncident as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident {incident_id!r} in this organisation",
        ) from missing
    return _row(closed)


@router.post("/incidents/{incident_id}/suppress", response_model=IncidentSummaryView)
async def suppress_incident(
    incident_id: str,
    request: SuppressRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IncidentSummaryView:
    """Close an incident as suppressed, naming what covered it."""
    try:
        suppressed = await _incidents(state).suppress(
            auth.scope,
            incident_id,
            by=request.rule,
            reason=request.reason,
            actor=auth.principal_id,
            now=datetime.now(UTC),
        )
    except UnknownIncident as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident {incident_id!r} in this organisation",
        ) from missing
    return _row(suppressed)


@router.get("/detectors", response_model=DetectorListView)
async def list_detectors(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DetectorListView:
    """Return every declared detector, its coverage, and what it concludes now."""
    detectors = await _detectors(state, auth)
    views = await detectors.list(auth.scope, now=datetime.now(UTC))
    return DetectorListView(
        detectors=[_detector(view) for view in views],
        paused=detectors.paused,
        pause_reason=detectors.pause_reason,
    )


@router.get("/observations", response_model=ObservationListView)
async def list_observations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = MAX_INCIDENT_PAGE_SIZE,
) -> ObservationListView:
    """Return what every enabled detector concludes right now."""
    detectors = await _detectors(state, auth)
    seen = await detectors.observations(auth.scope, now=datetime.now(UTC), limit=limit)
    return ObservationListView(observations=[_observation(entry) for entry in seen])


@router.post("/detectors/{detector_id}/dry-run", response_model=DryRunView)
async def dry_run_detector(
    detector_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DryRunView:
    """Return what a detector would conclude against stored signals, firing nothing."""
    detectors = await _detectors(state, auth)
    try:
        run = await detectors.dry_run(auth.scope, detector_id, now=datetime.now(UTC))
    except UnknownDetector as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no detector {detector_id!r} is declared for this team",
        ) from missing
    return DryRunView(
        detector_id=detector_id,
        would_fire=run.would_fire,
        observations=[_observation(entry) for entry in run.observations],
        fired=False,
    )


@router.post("/detectors/{detector_id}/enable", response_model=DetectorSummaryView)
async def enable_detector(
    detector_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DetectorSummaryView:
    """Turn a detector on for this team, through the configuration service."""
    return await _toggle(state, auth, detector_id, enabled=True)


@router.post("/detectors/{detector_id}/disable", response_model=DetectorSummaryView)
async def disable_detector(
    detector_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DetectorSummaryView:
    """Turn a detector off for this team, without unconfiguring it."""
    return await _toggle(state, auth, detector_id, enabled=False)


async def _toggle(
    state: GatewayState,
    auth: AuthenticatedRequest,
    detector_id: str,
    *,
    enabled: bool,
) -> DetectorSummaryView:
    """Write the enabled flag through configuration and return the detector's row.

    The write lands on the caller's own node, which makes an inherited set local
    to that node. That is the honest reading of "this team turned this off": a
    team overriding what it inherited, rather than silently editing the
    division's configuration for everybody.
    """
    node_id = auth.team_node_id or auth.scope.org_id
    detectors = await _detectors(state, auth)
    try:
        patch = detectors.settings_with(detector_id, enabled=enabled)
    except UnknownDetector as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no detector {detector_id!r} is declared for this team",
        ) from missing

    await _config(state, auth).set_settings(
        node_id, patch, actor_id=auth.principal_id, actor_kind=ActorKind.USER
    )

    refreshed = await _detectors(state, auth)
    for view in await refreshed.list(auth.scope, now=datetime.now(UTC)):
        if view.declaration.detector_id == detector_id:
            return _detector(view)
    raise HTTPException(  # pragma: no cover — the write above just stored it
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"no detector {detector_id!r} is declared for this team",
    )


__all__ = ["router"]
