"""Running the topology discovery job the scheduler can now dispatch.

``topology_discovery_job`` says reconciliation is part of the job rather than a
second one, because "a discovery run whose result is never applied has observed
the estate and told nobody". It was defensible right up to the point where
nothing ran the job at all — which is where it has been since it was written.

The runner is the adapter, not the mechanism: the sweep, the enrichment and the
graph write are ``EnrichingSweeper``'s, with their own suite. What this adds is
the two things the payload carries and the sweeper cannot infer — which source
to read, and whether the operator asked for a full pass or an incremental one.

**A reader this deployment does not have is refused by name.** Sweeping nothing
and reporting success would leave an estate quietly ageing behind a job that
looks healthy, which is the failure mode the whole discovery feature is written
against.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.estate.discovery.enriched import EnrichedSweep
from platform.estate.discovery.port import DiscoveryMode, ResourceReader, SweepBudget
from platform.estate.discovery.schedule import PAYLOAD_MODE, PAYLOAD_SOURCE, zones_of
from platform.estate.enrichment import EnrichmentPlan, ZoneMap
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_snapshot_store import EstateDailySnapshot
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.scheduler.dispatch import JobContext

logger = get_logger(__name__)


class UnknownDiscoverySource(LookupError):
    """A scheduled job names a discovery source this deployment cannot read."""

    def __init__(self, source: str, known: tuple[str, ...]) -> None:
        super().__init__(
            f"No discovery reader named {source or '(none)'!r} is configured. "
            f"This deployment can discover: {', '.join(known) or 'nothing'}."
        )
        self.source = source
        self.known = known


@runtime_checkable
class EnrichingSweep(Protocol):
    """What the runner needs from the sweeper: one pass, fully applied."""

    async def sweep(
        self,
        scope: TenantScope,
        reader: ResourceReader,
        *,
        plan: EnrichmentPlan,
        now: datetime,
        mode: DiscoveryMode = DiscoveryMode.FULL,
        budget: SweepBudget | None = None,
        source: str = "",
    ) -> EnrichedSweep:
        """Sweep ``reader``, annotate what it stored, and write the graph."""


def _mode(context: JobContext) -> DiscoveryMode:
    """Return the mode the payload asks for, defaulting to full.

    Full rather than raising on a value somebody hand-edited, for the reason
    ``schedule.mode_of`` gives: an unrecognised mode should cost provider calls,
    not a sweep that never runs and an estate that quietly goes stale.
    """
    raw = context.named(PAYLOAD_MODE, DiscoveryMode.FULL.value)
    return (
        DiscoveryMode.INCREMENTAL if raw == DiscoveryMode.INCREMENTAL.value else DiscoveryMode.FULL
    )


@dataclass(slots=True)
class TopologyDiscoveryRunner:
    """Runs the discovery pass one claimed ``topology.discovery`` job names."""

    readers: Mapping[str, ResourceReader]
    sweeper: EnrichingSweep
    #: What the operator declared about each source, by source name. A
    #: deployment that has declared nothing sweeps and writes the graph without
    #: annotations, which is the documented degradation rather than a refusal.
    plans: Mapping[str, EnrichmentPlan] = field(default_factory=dict)
    #: Where the day's estate snapshot is confirmed after this sweep. ``None``
    #: skips it — the shape every test double that only cares about the sweep
    #: itself already constructs, and the composition root is the one caller
    #: that wires a real one, because deciding whether a deployment keeps this
    #: history is a composition concern, not the sweep's.
    gateway: PersistenceGateway | None = None

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Sweep the named source, apply what was declared, and report it all."""
        name = context.named(PAYLOAD_SOURCE)
        reader = self.readers.get(name)
        if reader is None:
            raise UnknownDiscoverySource(name, tuple(self.readers))

        # The declared networks travel with the job, so a deployment that
        # registered one source per cluster places each one the way its own
        # preview did. A plan composed for the source still wins, because that
        # is the operator's standing declaration rather than one registration's.
        declared = zones_of(context.payload)
        plan = self.plans.get(name)
        if plan is None:
            plan = EnrichmentPlan(zones=ZoneMap.of(declared)) if declared else EnrichmentPlan()

        result = await self.sweeper.sweep(
            context.scope,
            reader,
            plan=plan,
            now=context.fire_time,
            mode=_mode(context),
            source=name,
        )
        await self._confirm_daily_snapshot(context.scope, now=context.fire_time)
        return record_of(result)

    async def _confirm_daily_snapshot(self, scope: TenantScope, *, now: datetime) -> None:
        """Record today's whole-estate counts, once.

        Read from `EstateRepository.summarise` rather than from anything this
        sweep itself just ingested, because the daily figure is about the
        *whole* estate — every source, not only the one this job just swept —
        and `record` is idempotent by day, so a fifteen-minute sweep of ten
        different sources confirms one row rather than writing ten candidates
        for the same point on the sparkline.
        """
        if self.gateway is None:
            return
        async with self.gateway.begin(scope) as uow:
            summary = await uow.estate.summarise(now=now)
            await uow.estate_snapshots.record(
                EstateDailySnapshot(
                    snapshot_date=now.date(),
                    total=summary.total,
                    captured_at=now,
                    counts_by_kind=dict(summary.by_kind),
                    counts_by_health=dict(summary.by_health),
                )
            )


def record_of(result: EnrichedSweep) -> dict[str, Any]:
    """Return the JSON-serialisable record one enriched sweep leaves behind.

    Zones and domains are carried rather than left to be read back off the
    graph: a deployment without a graph store degrades to zero here, and
    zero-because-degraded and zero-because-empty are different mornings.
    """
    sweep = result.sweep
    return {
        "source": sweep.source,
        "outcome": sweep.outcome.value,
        "mode": sweep.mode.value,
        "discovered": sweep.discovered,
        "provider_calls": sweep.provider_calls,
        "absent": list(sweep.absent),
        "stale": list(sweep.stale),
        "reason": sweep.reason,
        "enrichment": result.enrichment.to_record(),
        "zones": result.zones,
        "domains": result.domains,
    }


__all__ = [
    "EnrichingSweep",
    "TopologyDiscoveryRunner",
    "UnknownDiscoverySource",
    "record_of",
]
