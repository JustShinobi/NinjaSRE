"""One discovery pass, and the strict order that makes its conclusions safe.

Read, then ingest, then conclude, then record. The order is the design: nothing
concludes anything about what it did not see until the reading has finished and
the source has said it finished. Three separate paths reach "conclude nothing":

- the read raised, so the sweep failed and its resources are marked *stale* with
  the reason — never absent, because an integration outage is not a
  decommissioning and treating it as one cascades into every detector and every
  autonomy decision downstream;
- the sweep hit a bound and suspended at a cursor, so it saw part of the
  inventory and the rest is not missing, merely unread;
- the sweep was incremental, so it saw a delta, and a delta says nothing about
  what is absent from it.

Only a **full sweep that ran to completion** may mark anything absent, and
``SweepReport.concluded_absence`` is the one expression that decides.

**No credential passes through this module.** The sweep holds a persistence
gateway, a kind registry and a clock. It calls ``ResourceReader.discover``,
whose signature has nowhere to put a secret, and the reader reaches its provider
through the credential proxy exactly like every other integration call. A test
reads this module's own source to assert it.

Concurrency is the scheduler's rather than this module's: two replicas are kept
off one source by the same lease-based claiming that stops two replicas running
one job, which ``schedule`` wires. When a race happens anyway the sweep
*converges* rather than duplicating, because identities, sweep identifiers and
transition keys are all derived — two replicas reaching the same conclusion
write the same rows rather than two sets of them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from platform.estate.discovery.port import (
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    ResourceReader,
    SweepBudget,
)
from platform.estate.discovery.reconcile import Reconciled, reconcile
from platform.estate.errors import NoStableIdentifier, UnknownResourceKind
from platform.estate.health.derive import derive_from
from platform.estate.health.mapping import StatusMapping
from platform.estate.identity import derive_resource_id
from platform.estate.kinds import KindRegistry
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_repository import SweepOutcome, SweepRecord
from platform.persistence.ports.topology_graph import EdgeKind, NodeKind, TopologyEdge, TopologyNode
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep did, in the terms an operator would ask about.

    Returned as well as stored. The stored ``SweepRecord`` is what the next
    sweep resumes from; this is what the caller logs, shows, and asserts on, and
    it carries what a record has no column for — which attributes were dropped,
    which kinds were skipped, which resources could not be named.
    """

    source: str
    outcome: SweepOutcome
    mode: DiscoveryMode
    started_at: datetime
    completed_at: datetime
    #: The row this sweep wrote. Carried so a post-step can add what it
    #: concluded to the same record rather than deriving the identifier from
    #: two fields and a convention it would have to keep in step.
    sweep_id: str = ""
    discovered: int = 0
    provider_calls: int = 0
    cursor: str = ""
    reason: str = ""
    absent: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    dropped_attributes: tuple[str, ...] = ()
    screened_attributes: tuple[str, ...] = ()
    skipped_kinds: tuple[str, ...] = ()
    unidentified: int = 0

    @property
    def concluded_absence(self) -> bool:
        """Return whether this sweep was entitled to decide something was gone.

        The one expression in the feature that grants that entitlement. A full
        sweep that ran to completion, and nothing else: a failure saw an error,
        a suspension saw a page, and an incremental pass saw a delta.
        """
        return self.outcome is SweepOutcome.SUCCEEDED and self.mode is DiscoveryMode.FULL


@dataclass(slots=True)
class _Gathered:
    """What one read produced, before anything has been written or concluded."""

    reconciled: list[Reconciled] = field(default_factory=list)
    dropped: set[str] = field(default_factory=set)
    screened: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    unidentified: int = 0
    provider_calls: int = 0
    cursor: str = ""
    complete: bool = False
    statuses: dict[str, tuple[str, dict[str, str]]] = field(default_factory=dict)


@dataclass(slots=True)
class EstateSweeper:
    """Runs one discovery pass against one source, for one tenant.

    Holds no credential and no vendor client — only the store, the kinds this
    deployment models, an optional per-source status mapping, and a clock. The
    clock is injected because the time bound is the one thing a test cannot wait
    for honestly.
    """

    gateway: PersistenceGateway
    kinds: KindRegistry
    mappings: dict[str, StatusMapping] = field(default_factory=dict)
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def sweep(
        self,
        scope: TenantScope,
        reader: ResourceReader,
        *,
        now: datetime,
        mode: DiscoveryMode = DiscoveryMode.FULL,
        budget: SweepBudget | None = None,
        source: str = "",
    ) -> SweepReport:
        """Run one pass and return what it did.

        ``source`` overrides the integration named on the declaration, for a
        deployment with two of one vendor connected. Everything downstream —
        identity, absence, staleness — is scoped by it.
        """
        declaration = reader.declaration
        integration = source or declaration.integration
        effective = _resolved_mode(mode, declaration)
        spend = budget if budget is not None else SweepBudget.for_declaration(declaration)
        resumed, began = await self._resume_point(scope, integration, now)

        try:
            gathered = await self._read(
                scope,
                reader,
                source=integration,
                mode=effective,
                cursor=resumed,
                budget=spend,
                at=now,
            )
        except Exception as failure:  # noqa: BLE001 — every provider failure lands here
            return await self._failed(scope, integration, effective, now, failure)

        return await self._ingest(
            scope, gathered, source=integration, mode=effective, now=now, began=began
        )

    # --- reading --------------------------------------------------------------

    async def _read(
        self,
        scope: TenantScope,
        reader: ResourceReader,
        *,
        source: str,
        mode: DiscoveryMode,
        cursor: str,
        budget: SweepBudget,
        at: datetime,
    ) -> _Gathered:
        """Page through the source until it finishes or the budget runs out.

        Reconciliation happens here — inside the read — because deciding a
        resource's identity needs the estate, and doing it per page keeps the
        write transaction below short rather than holding it open across every
        provider call.
        """
        gathered = _Gathered()
        started = self.clock()

        async with self.gateway.begin(scope) as uow:
            while True:
                page = await reader.discover(mode=mode, cursor=cursor, budget=budget)
                gathered.provider_calls += max(page.provider_calls, 1)
                await self._absorb(uow, page, gathered, source=source, at=at)
                gathered.cursor = page.cursor
                gathered.complete = page.complete

                if page.complete:
                    break
                elapsed = (self.clock() - started).total_seconds()
                if _bound_reached(gathered, budget=budget, elapsed_seconds=elapsed):
                    break
                cursor = page.cursor

        return gathered

    async def _absorb(
        self,
        uow: UnitOfWork,
        page: DiscoveryPage,
        gathered: _Gathered,
        *,
        source: str,
        at: datetime,
    ) -> None:
        """Reconcile one page's resources, skipping the ones that cannot be stored.

        A resource of an unknown kind and a resource with no stable identifier
        are both *skipped and named*, never abandoned-with-the-page. A provider
        that reports one malformed guest among two hundred good ones should cost
        the estate that guest, not the sweep.
        """
        for reported in page.resources:
            parent_id = (
                derive_resource_id(source=source, native_id=reported.parent_native_id)
                if reported.parent_native_id.strip()
                else None
            )
            try:
                outcome = await reconcile(
                    uow.estate,
                    reported,
                    source=source,
                    kinds=self.kinds,
                    parent_id=parent_id,
                    at=at,
                )
            except UnknownResourceKind:
                gathered.skipped.add(reported.kind)
                continue
            except NoStableIdentifier:
                gathered.unidentified += 1
                continue

            gathered.reconciled.append(outcome)
            gathered.dropped.update(outcome.dropped)
            gathered.dropped.update(outcome.invalid)
            gathered.screened.update(outcome.screened)
            gathered.statuses[outcome.resource.resource_id] = (
                reported.provider_status,
                dict(reported.signals),
            )

    # --- outcomes -------------------------------------------------------------

    async def _ingest(
        self,
        scope: TenantScope,
        gathered: _Gathered,
        *,
        source: str,
        mode: DiscoveryMode,
        now: datetime,
        began: datetime,
    ) -> SweepReport:
        """Write what was read, conclude what may be concluded, record the sweep.

        ``began`` is when this sweep *chain* started, which is ``now`` for a
        sweep that ran in one pass and the earlier instant for one that
        suspended and resumed. It is what the absence pass measures against, so
        that a resumption does not decommission everything its own first pass
        ingested.
        """
        outcome = SweepOutcome.SUCCEEDED if gathered.complete else SweepOutcome.SUSPENDED
        report = SweepReport(
            sweep_id=_sweep_id(source, began),
            source=source,
            outcome=outcome,
            mode=mode,
            started_at=began,
            completed_at=now,
            discovered=len(gathered.reconciled),
            provider_calls=gathered.provider_calls,
            cursor="" if gathered.complete else gathered.cursor,
            dropped_attributes=tuple(sorted(gathered.dropped)),
            screened_attributes=tuple(sorted(gathered.screened)),
            skipped_kinds=tuple(sorted(gathered.skipped)),
            unidentified=gathered.unidentified,
        )

        async with self.gateway.begin(scope) as uow:
            seen: list[str] = []
            for entry in gathered.reconciled:
                stored = await uow.estate.upsert(entry.resource)
                seen.append(stored.resource_id)
                raw_status, signals = gathered.statuses.get(stored.resource_id, ("", {}))
                await uow.estate.record_health(
                    stored.resource_id,
                    derive_from(
                        raw_status=raw_status,
                        signals=signals,
                        at=now,
                        source=source,
                        mapping=self.mappings.get(source),
                    ),
                )
                await _record_in_graph(uow, entry, source=source)

            absent: tuple[str, ...] = ()
            if report.concluded_absence:
                absent = await uow.estate.mark_absent(
                    source=source, seen_ids=frozenset(seen), at=now, since=began
                )

            await uow.estate.record_sweep(
                SweepRecord(
                    sweep_id=_sweep_id(source, began),
                    source=source,
                    started_at=began,
                    outcome=outcome,
                    completed_at=now,
                    seen_count=len(seen),
                    provider_calls=gathered.provider_calls,
                    cursor=report.cursor,
                )
            )

        _log(report, absent=absent)
        return _with(report, absent=absent)

    async def _failed(
        self,
        scope: TenantScope,
        source: str,
        mode: DiscoveryMode,
        now: datetime,
        failure: Exception,
    ) -> SweepReport:
        """Mark this source's resources stale, record the failure, conclude nothing.

        The whole of FR-010 is here, and it is deliberately the shortest branch
        in the module: there is no path from this method to ``mark_absent``.
        """
        reason = f"{type(failure).__name__}: {failure}"
        async with self.gateway.begin(scope) as uow:
            stale = await uow.estate.mark_stale(source=source, at=now, reason=reason)
            await uow.estate.record_sweep(
                SweepRecord(
                    sweep_id=_sweep_id(source, now),
                    source=source,
                    started_at=now,
                    outcome=SweepOutcome.FAILED,
                    completed_at=now,
                    reason=reason,
                )
            )

        logger.warning("estate.sweep_failed", source=source, reason=reason, stale=len(stale))
        return SweepReport(
            sweep_id=_sweep_id(source, now),
            source=source,
            outcome=SweepOutcome.FAILED,
            mode=mode,
            started_at=now,
            completed_at=now,
            reason=reason,
            stale=stale,
        )

    async def _resume_point(
        self,
        scope: TenantScope,
        source: str,
        now: datetime,
    ) -> tuple[str, datetime]:
        """Return the cursor to resume from and the instant this chain began.

        Only a *suspended* sweep leaves a cursor. A failed sweep's would resume
        from a page nobody successfully read, and a successful one has nothing
        left to resume — so both start again at the beginning, now.

        A resumption keeps the suspended sweep's ``started_at`` as the chain's
        beginning, so one logical sweep is one record however many passes it
        takes, and the absence pass has an honest instant to measure against.
        """
        async with self.gateway.begin(scope) as uow:
            previous = await uow.estate.last_sweep(source)
        if previous is None or previous.outcome is not SweepOutcome.SUSPENDED:
            return "", now
        return previous.cursor, previous.started_at


# --- module-level rules ---------------------------------------------------------


def _resolved_mode(requested: DiscoveryMode, declaration: DiscoveryDeclaration) -> DiscoveryMode:
    """Return the mode this source can actually answer in.

    A source asked for an incremental answer it cannot give falls back to a full
    one rather than failing. The fallback is safe in the direction that matters:
    a full sweep concludes everything an incremental one can, and the reverse is
    what would be dangerous.
    """
    if requested is DiscoveryMode.INCREMENTAL and not declaration.supports_incremental:
        return DiscoveryMode.FULL
    return requested


def _sweep_id(source: str, at: datetime) -> str:
    """Return the identifier one sweep of one source at one instant gets.

    Derived rather than random, for the reason every other key in this feature
    is: two replicas that both started this sweep record one row.
    """
    return f"{source}@{at.astimezone(UTC).isoformat()}"


def _bound_reached(
    gathered: _Gathered,
    *,
    budget: SweepBudget,
    elapsed_seconds: float,
) -> bool:
    """Return whether the sweep must stop before asking for another page.

    Three bounds, one answer. Stopping is not truncation: the cursor is kept and
    the next sweep resumes from it, so what went unread stays unread rather than
    becoming unseen.
    """
    return (
        gathered.provider_calls >= budget.max_provider_calls
        or len(gathered.reconciled) >= budget.max_resources
        or elapsed_seconds >= budget.max_seconds
    )


async def _record_in_graph(uow: UnitOfWork, entry: Reconciled, *, source: str) -> None:
    """Record the resource and its parentage in the knowledge graph.

    The graph rather than a second one: blast radius already traverses it, and
    two graphs would mean two answers to "what does this affect". A changed
    parent deletes the old edge rather than leaving it, because every traversal
    returns *nodes* and a caller reading them cannot tell a retired edge from a
    live one.

    Topology may be unavailable — a deployment without Apache AGE degrades
    rather than crashing — so this never raises into the sweep. An estate
    without a graph is a smaller answer; an estate that failed to ingest
    because the graph was missing is no answer at all.
    """
    resource = entry.resource
    availability = await uow.topology.availability()
    if not availability.available:
        return

    await uow.topology.upsert_node(
        TopologyNode(
            node_id=resource.resource_id,
            kind=NodeKind.RESOURCE,
            name=resource.display_name or resource.resource_id,
            owner_node_id=resource.team_node_id,
            properties={"kind": resource.kind, "source": source},
        )
    )
    if resource.parent_id is None:
        return

    for existing in await uow.topology.edges_from(resource.resource_id):
        if existing.kind is EdgeKind.HOSTED_ON and existing.to_node_id != resource.parent_id:
            await uow.topology.delete_edge(existing)

    await uow.topology.upsert_edge(
        TopologyEdge(
            from_node_id=resource.resource_id,
            to_node_id=resource.parent_id,
            kind=EdgeKind.HOSTED_ON,
        )
    )


def _with(report: SweepReport, *, absent: Sequence[str]) -> SweepReport:
    """Return ``report`` carrying what the absence pass concluded."""
    return SweepReport(
        sweep_id=report.sweep_id,
        source=report.source,
        outcome=report.outcome,
        mode=report.mode,
        started_at=report.started_at,
        completed_at=report.completed_at,
        discovered=report.discovered,
        provider_calls=report.provider_calls,
        cursor=report.cursor,
        reason=report.reason,
        absent=tuple(absent),
        stale=report.stale,
        dropped_attributes=report.dropped_attributes,
        screened_attributes=report.screened_attributes,
        skipped_kinds=report.skipped_kinds,
        unidentified=report.unidentified,
    )


def _log(report: SweepReport, *, absent: Sequence[str]) -> None:
    """Record what the sweep did, once, rather than once per resource."""
    logger.info(
        "estate.sweep",
        source=report.source,
        outcome=report.outcome.value,
        mode=report.mode.value,
        discovered=report.discovered,
        absent=len(absent),
        provider_calls=report.provider_calls,
        dropped_attributes=list(report.dropped_attributes),
        skipped_kinds=list(report.skipped_kinds),
        unidentified=report.unidentified,
    )


__all__ = ["EstateSweeper", "SweepReport"]
