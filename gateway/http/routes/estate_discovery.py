"""Looking at what a source would discover, before anything is stored.

Two routes, and the first one is the whole reason this module exists separately
from ``routes/estate.py``: the estate's other routes read what the deployment
already knows, and these two are about the moment before it knows anything.

**Preview stores nothing.** It runs the source's own ``discover`` and returns
counts — nodes, guests, how many are running, how many the zone map places. No
reconciliation, no upsert, no sweep record, no absence pass. An operator sees
"2 nodes, 57 containers, 49 running, 7 zones" and recognises their own cluster,
which is what turns a form into a confirmation. If they do not recognise it,
nothing has to be undone.

**Confirming registers the source and then gets out of the way.** It writes the
recurring sweep job the scheduler already knows how to claim, at the interval
the source itself declares. There is no second scheduler and no discovery loop
here: the job goes into the same store, is claimed with the same lease, and is
divided between replicas by the same mechanism that stops two of them running
one investigation.

The counts are computed from the same page a sweep would ingest, so a preview
that says 57 and a sweep that stores 52 is a discrepancy in the source rather
than between two ways of counting.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.state import GatewayState
from platform.estate.discovery.enriched import enrichment_findings
from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryMode,
    ResourceReader,
    SweepBudget,
)
from platform.estate.discovery.schedule import next_run_after, sweep_job
from platform.estate.enrichment import ZoneMap
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE, KIND_VIRTUAL_MACHINE
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_repository import SweepRecord

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/estate/discovery", tags=["estate"])

#: The statuses a provider uses for "this is up". Counted rather than derived
#: through the health mapping, because a preview has not stored anything for a
#: mapping to be applied to — and "49 running" is the operator's own word.
_RUNNING: frozenset[str] = frozenset({"running", "online", "started"})

#: The kinds a zone is expected of. A node sits on a management network and a
#: guest on a workload one; a datastore and a backup job sit on neither, and
#: counting them as unplaced would bury the guest that genuinely is.
_ON_A_NETWORK: frozenset[str] = frozenset({KIND_NODE, KIND_CONTAINER, KIND_VIRTUAL_MACHINE})


class DiscoveryPreviewRequest(BaseModel):
    """What to preview, and what to place its resources into.

    ``zones`` is optional and is a plain CIDR-to-name mapping rather than an
    ingestion of the operator's inventory: the preview happens before anything
    is stored, so it must be answerable from what the request carries plus what
    the provider says. A preview with no zone map reports every resource as
    unplaced, which is honest rather than empty.
    """

    integration: str = Field(min_length=1)
    zones: dict[str, str] = Field(default_factory=dict)


class DiscoveryPreviewView(BaseModel):
    """What a sweep would find, counted, with nothing written."""

    integration: str
    #: Whether the source reached the end of its inventory in one page. A
    #: preview that suspended is reporting a floor, and saying so is the
    #: difference between "57 containers" and "at least 57 containers".
    complete: bool
    provider_calls: int
    total: int
    nodes: int
    guests: int
    running: int
    zones: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_zone: dict[str, int] = Field(default_factory=dict)
    #: Guests whose address no declared zone covers. Reported here rather than
    #: hidden, because a preview whose zone count looks right while eleven
    #: guests fell outside it is the wrong kind of reassuring.
    unplaced: int = 0


class DiscoverySourceView(BaseModel):
    """The sweep this deployment will now run, and when it next comes due."""

    integration: str
    job_id: str
    interval_seconds: int
    next_run_at: datetime


class DivergenceView(BaseModel):
    """One disagreement between the declared inventory and the live source."""

    kind: str
    subject: str
    detail: str


class DiscoveryReportView(BaseModel):
    """The last sweep of one source, and what it disagreed with the file about."""

    source: str
    outcome: str
    started_at: datetime
    completed_at: datetime | None = None
    seen_count: int = 0
    provider_calls: int = 0
    reason: str = ""
    annotated: int = 0
    divergences: list[DivergenceView] = Field(default_factory=list)


class DiscoveryReportListView(BaseModel):
    """One report per source that has ever been swept, in name order."""

    reports: list[DiscoveryReportView] = Field(default_factory=list)


def _annotated(findings: Mapping[str, object]) -> int:
    """Return how many resources the enrichment annotated, or nought.

    Read defensively because the findings are a stored document rather than a
    typed record: a sweep written by an older build, or by a post-step that
    changes shape, must render as "nothing was concluded" instead of raising in
    a route somebody opened during an incident.
    """
    counted = findings.get("annotated", 0)
    return counted if isinstance(counted, int) and not isinstance(counted, bool) else 0


def _report(record: SweepRecord) -> DiscoveryReportView:
    """Return one sweep record as the document a console and the CLI read."""
    findings = enrichment_findings(record.findings)
    divergences = findings.get("divergences", [])
    return DiscoveryReportView(
        source=record.source,
        outcome=record.outcome.value,
        started_at=record.started_at,
        completed_at=record.completed_at,
        seen_count=record.seen_count,
        provider_calls=record.provider_calls,
        reason=record.reason,
        annotated=_annotated(findings),
        divergences=[
            DivergenceView(
                kind=str(entry.get("kind", "")),
                subject=str(entry.get("subject", "")),
                detail=str(entry.get("detail", "")),
            )
            for entry in (divergences if isinstance(divergences, list) else [])
        ],
    )


def _reader(state: GatewayState, integration: str) -> ResourceReader:
    """Return the composed source for ``integration``, or refuse naming it."""
    reader = state.discovery_sources.get(integration)
    if reader is None:
        raise not_found(
            f"No discovery source for {integration!r} is composed in this deployment. A "
            f"source needs a vendor client, and a client needs the credential proxy, so "
            f"it is wired at composition rather than built from a request. Store the "
            f"credential first with PUT /v1/integrations/{integration}/credential."
        )
    return reader


def _address(resource: DiscoveredResource) -> str:
    """Return the address a resource reported, or empty when it reported none."""
    return str(resource.signals.get("address", ""))


def _counts(
    resources: Sequence[DiscoveredResource],
    *,
    zones: ZoneMap,
) -> tuple[dict[str, int], dict[str, int], int, int]:
    """Return per-kind counts, per-zone counts, how many run, and how many are unplaced."""
    by_kind: dict[str, int] = {}
    by_zone: dict[str, int] = {}
    running = 0
    unplaced = 0

    for resource in resources:
        by_kind[resource.kind] = by_kind.get(resource.kind, 0) + 1
        if resource.provider_status in _RUNNING:
            running += 1
        if resource.kind not in _ON_A_NETWORK:
            continue
        zone = zones.zone_for(_address(resource))
        if zone:
            by_zone[zone] = by_zone.get(zone, 0) + 1
        else:
            unplaced += 1

    return dict(sorted(by_kind.items())), dict(sorted(by_zone.items())), running, unplaced


@router.post("/preview", response_model=DiscoveryPreviewView)
async def preview_discovery(
    request: DiscoveryPreviewRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DiscoveryPreviewView:
    """Return what one pass over ``integration`` would find, storing none of it.

    Raises:
        ApiProblem: no source for that integration is composed (404).
    """
    del auth
    reader = _reader(state, request.integration)
    zones = ZoneMap.of(request.zones)
    page = await reader.discover(
        mode=DiscoveryMode.FULL,
        cursor="",
        budget=SweepBudget.for_declaration(reader.declaration),
    )

    by_kind, by_zone, running, unplaced = _counts(page.resources, zones=zones)
    logger.info(
        "estate.discovery_previewed",
        integration=request.integration,
        total=len(page.resources),
        complete=page.complete,
        provider_calls=page.provider_calls,
    )
    return DiscoveryPreviewView(
        integration=request.integration,
        complete=page.complete,
        provider_calls=page.provider_calls,
        total=len(page.resources),
        nodes=by_kind.get(KIND_NODE, 0),
        guests=by_kind.get(KIND_CONTAINER, 0) + by_kind.get(KIND_VIRTUAL_MACHINE, 0),
        running=running,
        zones=len(by_zone),
        by_kind=by_kind,
        by_zone=by_zone,
        unplaced=unplaced,
    )


@router.post("/sources", response_model=DiscoverySourceView)
async def register_discovery_source(
    request: DiscoveryPreviewRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DiscoverySourceView:
    """Register ``integration``'s recurring sweep, and say when it is next due.

    Due immediately. An operator who has just confirmed a preview expects the
    estate to fill, and a first sweep that waited out the declared interval
    would leave them looking at an empty screen for five minutes with nothing
    to distinguish "scheduled" from "broken".

    Raises:
        ApiProblem: no source for that integration is composed (404).
    """
    reader = _reader(state, request.integration)
    declaration = reader.declaration
    now = datetime.now(UTC)
    # The zones the operator just confirmed in the preview, carried into the
    # sweep. Without them the recurring pass places nothing, and the estate that
    # fills looks nothing like the preview that was approved.
    job = sweep_job(
        declaration,
        next_run_at=now,
        source=request.integration,
        zones=request.zones,
    )

    async with state.gateway.begin(auth.scope) as uow:
        stored = await uow.schedules.upsert_job(job)

    logger.info(
        "estate.discovery_source_registered",
        integration=request.integration,
        job_id=stored.job_id,
        interval_seconds=declaration.interval_seconds,
    )
    return DiscoverySourceView(
        integration=request.integration,
        job_id=stored.job_id,
        interval_seconds=declaration.interval_seconds,
        next_run_at=stored.next_run_at or next_run_after(declaration, now=now),
    )


@router.get("/report", response_model=DiscoveryReportListView)
async def discovery_report(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    source: str = "",
) -> DiscoveryReportListView:
    """Return each swept source's last pass and every disagreement it recorded.

    Divergence is content, so it is served rather than logged. Naming a
    ``source`` narrows to one and answers 404 when nothing has ever swept it —
    which is a different fact from a sweep that found nothing to disagree with,
    and collapsing the two would let an unconfigured deployment read as a
    perfectly reconciled one. Naming none returns what there is, which for a
    deployment that has swept nothing is an empty list.

    Raises:
        ApiProblem: a named source nothing has ever swept (404).
    """
    now = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        summary = await uow.estate.summarise(now=now)
        wanted = (source,) if source else tuple(sorted(summary.by_source))
        records = [await uow.estate.last_sweep(name) for name in wanted]

    found = [record for record in records if record is not None]
    if source and not found:
        raise not_found(
            f"No sweep of {source!r} has ever run in this deployment, so there is nothing "
            f"to report. Register the source with POST /v1/estate/discovery/sources."
        )
    return DiscoveryReportListView(reports=[_report(record) for record in found])


__all__ = ["router"]
