"""What the deployment is responsible for, and how each of it is doing.

Five routes over one service. The one shape worth explaining is that every
health value in a response is the *reported* state — absence, maintenance and
freshness already applied — and that the stored state travels beside it. A
client that received only one of them could not answer "stale as of what", and a
client that applied freshness itself would be a second copy of a rule that has
to have exactly one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from config.constants.estate import DEFAULT_TRANSITION_HISTORY, MAX_ESTATE_PAGE_SIZE
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.estate.service import EstateService, ResourceDetail, ResourceView
from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    EstateSummary,
    HealthDerivation,
    HealthTransition,
    ResourceHealth,
    ResourceReference,
)

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


class EstateSummaryView(BaseModel):
    total: int
    captured_at: datetime
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_health: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    problems: int = 0
    maintenance: int = 0
    absent: int = 0


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


def _detail(detail: ResourceDetail) -> ResourceDetailView:
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
    """Return one resource's state, why, its history, and what touched it."""
    detail = await _service(state).detail(
        auth.scope, resource_id, now=datetime.now(UTC), history=history
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no resource {resource_id!r} in this estate",
        )
    return _detail(detail)


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
