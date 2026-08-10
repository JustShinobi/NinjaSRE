"""What the deployment is responsible for, and how each of it is doing.

Five routes over one service. The one shape worth explaining is that every
health value in a response is the *reported* state — absence, maintenance and
freshness already applied — and that the stored state travels beside it. A
client that received only one of them could not answer "stale as of what", and a
client that applied freshness itself would be a second copy of a rule that has
to have exactly one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from config.constants.estate import (
    DEFAULT_TRANSITION_HISTORY,
    MAX_ESTATE_PAGE_SIZE,
    MAX_UNRESOLVED_ALERT_TARGETS,
)
from config.constants.observation import MAX_INCIDENT_PAGE_SIZE
from gateway.http.configured import configured_integrations
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.estate.alert_resolution import UnresolvedTargetFinding, unresolved_targets
from platform.estate.service import EstateService, ResourceDetail, ResourceView
from platform.estate.signal_map import SignalMap, signal_map_for
from platform.knowledge.base.estate_links import EstateLinker, LinkedDocument
from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    EstateSummary,
    HealthDerivation,
    HealthTransition,
    ResourceHealth,
    ResourceReference,
)
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentQuery

router = APIRouter(prefix="/v1/estate", tags=["estate"])

#: How many resources a listing returns when the caller does not say. Small
#: enough to render, large enough that a homelab's whole estate arrives in one
#: response.
DEFAULT_ESTATE_PAGE = 100


class SignalView(BaseModel):
    name: str
    value: str
    observed_at: datetime
    source: str = ""


class DerivationView(BaseModel):
    state: str
    rule: str
    derived_at: datetime
    signals: list[SignalView] = Field(default_factory=list)
    raw_status: str = ""
    explanation: str = ""


class ContributionView(BaseModel):
    integration: str
    native_id: str
    display_name: str = ""
    observed_at: datetime | None = None


class ResourceSummaryView(BaseModel):
    """One resource as a table row shows it."""

    resource_id: str
    kind: str
    display_name: str
    #: What to show. Absence, maintenance and freshness already applied.
    health: str
    #: What was last derived, before those overlays. An operator seeing
    #: ``stale`` needs this to know what it was stale *at*.
    stored_health: str
    is_stale: bool
    source: str
    sources: list[str] = Field(default_factory=list)
    native_id: str = ""
    #: What two descriptions of one thing agree on, and what a declared
    #: inventory is matched against. Served so a client can mark the rows a
    #: divergence report names without a second lookup per row.
    correlation_key: str = ""
    parent_id: str | None = None
    #: The parent's display name when the same read produced it, empty
    #: otherwise. A table shows this rather than the parent's identifier.
    parent_name: str = ""
    team_node_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    absent_since: datetime | None = None
    maintenance_until: datetime | None = None
    maintenance_reason: str = ""
    explanation: str = ""


class ResourceListView(BaseModel):
    resources: list[ResourceSummaryView]


class TransitionView(BaseModel):
    occurred_at: datetime
    state: str
    previous_state: str | None = None
    rule: str = ""
    signal: SignalView | None = None


class ReferenceView(BaseModel):
    reference_kind: str
    reference_id: str
    recorded_at: datetime
    summary: str = ""


class SignalSourceView(BaseModel):
    """Which source answers one question about this resource, and by what key."""

    question: str
    integration: str
    keyed_by: str
    key: str
    detail: str


class MissingSignalView(BaseModel):
    """A question nothing configured answers, and what would answer it."""

    question: str
    wanted: list[str] = Field(default_factory=list)
    why: str


class SignalsView(BaseModel):
    """Where an investigation of this resource should go for each question.

    Two lists rather than one with nulls in it. "Prometheus answers this, keyed
    by vmid" and "nothing answers this, loki or openobserve would" are different
    kinds of statement, and a client that had to inspect a field to tell them
    apart would render one as the other on the day somebody adds a field.
    """

    sources: list[SignalSourceView] = Field(default_factory=list)
    missing: list[MissingSignalView] = Field(default_factory=list)


class LinkedDocumentView(BaseModel):
    """One document somebody has written about this resource.

    ``matched`` and ``matched_on`` are served rather than kept internal because
    they are what lets an operator dismiss a link that is wrong: a list with no
    reason beside each entry is a list that has to be trusted whole.
    """

    document_id: str
    title: str
    location: str
    document_type: str
    matched: str = ""
    matched_on: str = ""


class ResourceDetailView(BaseModel):
    """One resource's page: its state, why, its history, and what touched it."""

    resource: ResourceSummaryView
    derivation: DerivationView | None = None
    rollup_rule: str
    freshness_seconds: int
    contributions: list[ContributionView] = Field(default_factory=list)
    transitions: list[TransitionView] = Field(default_factory=list)
    references: list[ReferenceView] = Field(default_factory=list)
    children: list[ResourceSummaryView] = Field(default_factory=list)
    parent: ResourceSummaryView | None = None
    #: Derived per request from what this team has configured, never stored. A
    #: map written down once is a map that is right until somebody connects a
    #: log store.
    signals: SignalsView = Field(default_factory=SignalsView)
    #: What has been written about this resource, from the corpus. Empty is the
    #: normal answer for most of any estate and for all of one whose corpus has
    #: not been synced, which is why it is a list rather than an absent block.
    documents: list[LinkedDocumentView] = Field(default_factory=list)


class EstateSummaryView(BaseModel):
    total: int
    captured_at: datetime
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_health: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    problems: int = 0
    maintenance: int = 0
    absent: int = 0


class UnresolvedTargetView(BaseModel):
    """An alert that arrived for something this estate does not hold."""

    value: str
    label: str
    zone: str
    why: str
    incident_id: str
    alert_name: str
    observed_at: str


class UnresolvedTargetListView(BaseModel):
    targets: list[UnresolvedTargetView] = Field(default_factory=list)


class MaintenanceRequest(BaseModel):
    """How long a resource is suppressed from the problem count, and why.

    ``reason`` is required and not defaulted. A maintenance window with no
    reason is one nobody can decide whether to extend, and the person who opened
    it will not be the person who finds it.
    """

    until: datetime
    reason: str = Field(min_length=1)


def _service(state: GatewayState) -> EstateService:
    return EstateService(gateway=state.gateway, kinds=state.estate_kinds)


def _unresolved(finding: UnresolvedTargetFinding) -> UnresolvedTargetView:
    return UnresolvedTargetView(
        value=finding.target.value,
        label=finding.target.label,
        zone=finding.target.zone,
        why=finding.target.why,
        incident_id=finding.incident_id,
        alert_name=finding.alert_name,
        observed_at=finding.observed_at.isoformat(),
    )


def _signal(signal: Any) -> SignalView:
    return SignalView(
        name=signal.name,
        value=signal.value,
        observed_at=signal.observed_at,
        source=signal.source,
    )


def _derivation(derivation: HealthDerivation | None) -> DerivationView | None:
    if derivation is None:
        return None
    return DerivationView(
        state=derivation.state.value,
        rule=derivation.rule,
        derived_at=derivation.derived_at,
        signals=[_signal(signal) for signal in derivation.signals],
        raw_status=derivation.raw_status,
        explanation=derivation.explanation,
    )


def _row(view: ResourceView) -> ResourceSummaryView:
    resource = view.resource
    return ResourceSummaryView(
        resource_id=resource.resource_id,
        kind=resource.kind,
        display_name=resource.display_name or resource.resource_id,
        health=view.health.value,
        stored_health=view.stored_health.value,
        is_stale=view.is_stale,
        source=resource.source,
        sources=[entry.integration for entry in resource.sources],
        native_id=resource.native_id,
        correlation_key=resource.correlation_key,
        parent_id=resource.parent_id,
        parent_name=view.parent_name,
        team_node_id=resource.team_node_id,
        labels=list(resource.labels),
        attributes=dict(resource.attributes),
        first_seen_at=resource.first_seen_at,
        last_seen_at=resource.last_seen_at,
        absent_since=resource.absent_since,
        maintenance_until=resource.maintenance_until,
        maintenance_reason=resource.maintenance_reason,
        explanation=view.explanation,
    )


def _transition(transition: HealthTransition) -> TransitionView:
    return TransitionView(
        occurred_at=transition.occurred_at,
        state=transition.state.value,
        previous_state=(
            transition.previous_state.value if transition.previous_state is not None else None
        ),
        rule=transition.rule,
        signal=_signal(transition.signal) if transition.signal is not None else None,
    )


def _reference(reference: ResourceReference) -> ReferenceView:
    return ReferenceView(
        reference_kind=reference.reference_kind.value,
        reference_id=reference.reference_id,
        recorded_at=reference.recorded_at,
        summary=reference.summary,
    )


def _summary(summary: EstateSummary) -> EstateSummaryView:
    return EstateSummaryView(
        total=summary.total,
        captured_at=summary.captured_at,
        by_kind=dict(summary.by_kind),
        by_health=dict(summary.by_health),
        by_source=dict(summary.by_source),
        problems=summary.problems,
        maintenance=summary.maintenance,
        absent=summary.absent,
    )


def _signals(found: SignalMap) -> SignalsView:
    return SignalsView(
        sources=[
            SignalSourceView(
                question=source.question,
                integration=source.integration,
                keyed_by=source.keyed_by,
                key=source.key,
                detail=source.detail,
            )
            for source in found.sources
        ],
        missing=[
            MissingSignalView(question=gap.question, wanted=list(gap.wanted), why=gap.why)
            for gap in found.missing
        ],
    )


def _document(entry: LinkedDocument) -> LinkedDocumentView:
    return LinkedDocumentView(
        document_id=entry.document_id,
        title=entry.title,
        location=entry.location,
        document_type=entry.document_type.value,
        matched=entry.matched,
        matched_on=entry.matched_on,
    )


def _detail(
    detail: ResourceDetail,
    signals: SignalMap,
    documents: Sequence[LinkedDocument] = (),
) -> ResourceDetailView:
    return ResourceDetailView(
        resource=_row(detail.view),
        derivation=_derivation(detail.view.derivation),
        rollup_rule=detail.view.rollup_rule.value,
        freshness_seconds=detail.view.freshness_seconds,
        contributions=[
            ContributionView(
                integration=entry.integration,
                native_id=entry.native_id,
                display_name=entry.display_name,
                observed_at=entry.observed_at,
            )
            for entry in detail.view.resource.sources
        ],
        transitions=[_transition(entry) for entry in detail.transitions],
        references=[_reference(entry) for entry in detail.references],
        children=[_row(child) for child in detail.children],
        parent=_row(detail.parent) if detail.parent is not None else None,
        signals=_signals(signals),
        documents=[_document(entry) for entry in documents],
    )


def _health_filter(values: list[str]) -> tuple[ResourceHealth, ...]:
    """Return the requested states, refusing one that is not in the closed set.

    Refusing rather than ignoring. A client asking for ``health=broken`` and
    receiving the whole estate would conclude that everything is broken.
    """
    states: list[ResourceHealth] = []
    for value in values:
        try:
            states.append(ResourceHealth(value))
        except ValueError as unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"{value!r} is not a health state. Expected one of: "
                    f"{', '.join(state.value for state in ResourceHealth)}."
                ),
            ) from unknown
    return tuple(states)


@router.get("/resources", response_model=ResourceListView)
async def list_resources(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    kind: list[str] = Query(default=[]),
    health: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    label: list[str] = Query(default=[]),
    team: str = "",
    parent: str = "",
    include_absent: bool = False,
    limit: int = DEFAULT_ESTATE_PAGE,
) -> ResourceListView:
    """Return the resources matching every filter given, by identifier."""
    query = EstateQuery(
        kinds=tuple(kind),
        health=_health_filter(health),
        sources=tuple(source),
        labels=tuple(label),
        team_node_id=team or None,
        parent_id=parent or None,
        include_absent=include_absent,
        limit=limit,
    )
    try:
        found = await _service(state).query(auth.scope, query, now=datetime.now(UTC))
    except BoundExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"a limit of {limit} exceeds the estate page bound of "
                f"{MAX_ESTATE_PAGE_SIZE}. Page through the estate rather than asking for it."
            ),
        ) from exceeded

    return ResourceListView(resources=[_row(view) for view in found])


@router.get("/unresolved-alert-targets", response_model=UnresolvedTargetListView)
async def list_unresolved_alert_targets(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> UnresolvedTargetListView:
    """Return the alert targets this estate does not hold, newest first.

    A finding of the same class as the reconciliation divergence a sweep
    produces, and read from the live incidents that recorded it rather than from
    a store of its own: the incident is already the record that the alert
    arrived, and a second one would be a second thing to expire.
    """
    async with state.gateway.begin(auth.scope) as uow:
        incidents = await uow.incidents.query(
            IncidentQuery(
                origins=(IncidentOrigin.ALERT,), live_only=True, limit=MAX_INCIDENT_PAGE_SIZE
            )
        )
    findings = unresolved_targets(incidents)[:MAX_UNRESOLVED_ALERT_TARGETS]
    return UnresolvedTargetListView(targets=[_unresolved(entry) for entry in findings])


@router.get("/summary", response_model=EstateSummaryView)
async def estate_summary(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> EstateSummaryView:
    """Return the estate in the numbers a dashboard tile shows."""
    summary = await _service(state).summarise(auth.scope, now=datetime.now(UTC))
    return _summary(summary)


@router.get("/resources/{resource_id}", response_model=ResourceDetailView)
async def resource_detail(
    resource_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    history: int = DEFAULT_TRANSITION_HISTORY,
) -> ResourceDetailView:
    """Return one resource's state, why, its history, and what touched it.

    The ``signals`` block is derived here rather than by the estate service,
    because it needs a fact the estate does not hold: which integrations this
    team has a credential for. Deriving it per request is also what keeps it
    correct — connect a log store and the next render of this page says so,
    with nothing to migrate.
    """
    detail = await _service(state).detail(
        auth.scope, resource_id, now=datetime.now(UTC), history=history
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no resource {resource_id!r} in this estate",
        )
    configured = await configured_integrations(state, auth)
    documents = await EstateLinker(gateway=state.gateway, scope=auth.scope).documents_for(
        resource_id
    )
    return _detail(detail, signal_map_for(detail.view.resource, configured=configured), documents)


@router.post("/resources/{resource_id}/maintenance", response_model=ResourceSummaryView)
async def enter_maintenance(
    resource_id: str,
    request: MaintenanceRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ResourceSummaryView:
    """Suppress a resource from the problem count until ``until``."""
    now = datetime.now(UTC)
    try:
        view = await _service(state).enter_maintenance(
            auth.scope, resource_id, until=request.until, reason=request.reason, at=now
        )
    except RecordNotFound as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no resource {resource_id!r} in this estate",
        ) from missing
    except BoundExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"that maintenance window is longer than a deployment may open in one go "
                f"({exceeded.limit}s). Reopen it when it expires rather than widening it."
            ),
        ) from exceeded
    return _row(view)


@router.delete("/resources/{resource_id}/maintenance", response_model=ResourceSummaryView)
async def leave_maintenance(
    resource_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ResourceSummaryView:
    """End a maintenance window now and return the resource as it reads."""
    try:
        view = await _service(state).leave_maintenance(
            auth.scope, resource_id, at=datetime.now(UTC)
        )
    except RecordNotFound as missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no resource {resource_id!r} in this estate",
        ) from missing
    return _row(view)


__all__ = ["router"]
