"""The topology discovery job, as the scheduler now runs it.

``topology_discovery_job`` has been definable since it was written and has never
run. Its own docstring says reconciliation is part of the job rather than a
second one — "a discovery run whose result is never applied has observed the
estate and told nobody" — and until there was a runner, *no* discovery run of
this kind observed anything at all.

Two properties, both about not lying to the operator afterwards.

**A reader this deployment does not have is a failure by name**, not a sweep of
nothing that reports success.

**The record says what the graph got.** Zones and domains are reported rather
than inferred, because a deployment without a graph store degrades to zero here
and zero-because-degraded and zero-because-empty are different mornings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from config.constants.knowledge import TOPOLOGY_DISCOVERY_JOB_KIND
from platform.estate.discovery.enriched import EnrichedSweep
from platform.estate.discovery.port import DiscoveryMode, ResourceReader, SweepBudget
from platform.estate.discovery.runner import TopologyDiscoveryRunner, UnknownDiscoverySource
from platform.estate.discovery.sweep import SweepOutcome, SweepReport
from platform.estate.enrichment import EnrichmentPlan, EnrichmentReport
from platform.persistence.ports import JobClaim, ScheduledJob, TenantScope
from platform.scheduler.dispatch import JobContext

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)


@dataclass(slots=True)
class StubReader:
    """A resource reader that is never actually read from here."""

    integration: str = "proxmox"


@dataclass(slots=True)
class StubSweeper:
    """An enriching sweeper that records how it was asked to sweep."""

    result: EnrichedSweep = field(
        default_factory=lambda: EnrichedSweep(
            sweep=SweepReport(
                source="proxmox",
                outcome=SweepOutcome.SUCCEEDED,
                mode=DiscoveryMode.FULL,
                started_at=EPOCH,
                completed_at=EPOCH,
                discovered=12,
            ),
            enrichment=EnrichmentReport(source="proxmox", annotated=4),
            zones=2,
            domains=1,
        )
    )
    asked: list[tuple[str, DiscoveryMode]] = field(default_factory=list)

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
        """Record the ask and answer with a fixed result."""
        self.asked.append((source, mode))
        return self.result


def context(payload: Mapping[str, object] | None = None) -> JobContext:
    """Return the context a worker hands a runner for one claimed firing."""
    job = ScheduledJob(
        job_id="topology.discovery:proxmox",
        name="Topology discovery: proxmox",
        kind=TOPOLOGY_DISCOVERY_JOB_KIND,
        schedule="*/30 * * * *",
        payload=dict(payload or {"source": "proxmox"}),
    )
    claim = JobClaim(
        claim_id="claim-1",
        job_id=job.job_id,
        org_id=ORG,
        worker_id="replica-a",
        claimed_at=EPOCH,
        lease_expires_at=EPOCH,
        payload=job.payload,
    )
    return JobContext(claim=claim, job=job, scope=TenantScope(org_id=ORG), fire_time=EPOCH)


async def test_the_run_sweeps_the_source_the_payload_names() -> None:
    sweeper = StubSweeper()
    runner = TopologyDiscoveryRunner(readers={"proxmox": StubReader()}, sweeper=sweeper)

    await runner.run(context())

    assert sweeper.asked == [("proxmox", DiscoveryMode.FULL)]


async def test_a_source_this_deployment_cannot_read_fails_by_name() -> None:
    runner = TopologyDiscoveryRunner(readers={"proxmox": StubReader()}, sweeper=StubSweeper())

    with pytest.raises(UnknownDiscoverySource, match="kubernetes"):
        await runner.run(context({"source": "kubernetes"}))


async def test_the_record_says_what_the_graph_got() -> None:
    runner = TopologyDiscoveryRunner(readers={"proxmox": StubReader()}, sweeper=StubSweeper())

    record = await runner.run(context())

    assert record["discovered"] == 12
    assert record["outcome"] == SweepOutcome.SUCCEEDED.value
    assert record["zones"] == 2
    assert record["domains"] == 1
    assert record["enrichment"]["annotated"] == 4


async def test_an_incremental_run_is_asked_for_when_the_payload_says_so() -> None:
    """A sweep that ran full when it could have run incremental costs provider calls."""
    sweeper = StubSweeper()
    runner = TopologyDiscoveryRunner(readers={"proxmox": StubReader()}, sweeper=sweeper)

    await runner.run(context({"source": "proxmox", "mode": DiscoveryMode.INCREMENTAL.value}))

    assert sweeper.asked == [("proxmox", DiscoveryMode.INCREMENTAL)]
