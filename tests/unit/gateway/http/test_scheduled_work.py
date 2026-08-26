"""The three job kinds, composed from what this deployment actually has.

A dispatcher and three runners still leave a deployment where nothing runs,
because the runners need collaborators only a composition root can build. This
is that root, and the suite holds it to the posture the rest of the state
already takes: **a missing source is named, not silent.**

The distinction that matters is between "no runner for this kind" and "no source
called that". The first is a hole in the build and should never be what an
operator sees for a kind that ships; the second is their own configuration
drifting, and the message has to say which one it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from config.constants.estate import ESTATE_DISCOVERY_JOB_KIND
from config.constants.knowledge import (
    CORPUS_SYNC_JOB_KIND,
    KNOWLEDGE_SYNC_JOB_KIND,
    TOPOLOGY_DISCOVERY_JOB_KIND,
)
from gateway.http.scheduled_work import dispatcher_for
from gateway.http.state import GatewayState
from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    SweepBudget,
)
from platform.estate.discovery.runner import TopologyDiscoveryRunner
from platform.estate.identity import derive_resource_id
from platform.estate.kinds import KIND_NODE, KIND_VIRTUAL_MACHINE
from platform.knowledge.base.sync.runner import UnknownSource
from platform.knowledge.topology.queries import TopologyQueries
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import JobClaim, ScheduledJob, TenantScope
from platform.scheduler.dispatch import JobContext

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)
DISCOVERY_SOURCE = "proxmox"


def context(kind: str, *, source: str = "wiki") -> JobContext:
    """Return the context a worker would hand a runner for ``kind``."""
    job = ScheduledJob(
        job_id=f"{kind}:{source}",
        name=f"{kind} for the suite",
        kind=kind,
        schedule="0 2 * * *",
        payload={"source": source},
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


def state_over(store: FakePersistence, **extra: object) -> GatewayState:
    """Return a gateway state with only what this suite reads wired."""
    return GatewayState(
        gateway=store,
        tokens=None,  # type: ignore[arg-type]
        investigator=None,  # type: ignore[arg-type]
        **extra,  # type: ignore[arg-type]
    )


async def test_the_three_kinds_that_had_no_runner_now_have_one() -> None:
    store = FakePersistence()
    try:
        dispatcher = dispatcher_for(state_over(store))
    finally:
        await store.close()

    assert set(dispatcher.kinds) >= {
        KNOWLEDGE_SYNC_JOB_KIND,
        CORPUS_SYNC_JOB_KIND,
        TOPOLOGY_DISCOVERY_JOB_KIND,
    }


async def test_a_deployment_with_nothing_wired_names_the_source_not_the_kind() -> None:
    """Their configuration drifted; this is not a hole in the build, and says so."""
    store = FakePersistence()
    try:
        dispatcher = dispatcher_for(state_over(store))
        result = await dispatcher.dispatch(context(KNOWLEDGE_SYNC_JOB_KIND))
    finally:
        await store.close()

    assert "wiki" in result.failure
    assert "can sync: nothing" in result.failure


async def test_the_discovery_runner_reads_the_sources_composition_wired() -> None:
    """One mapping, wired once: the sweep and the schedule see the same sources."""
    store = FakePersistence()
    reader = object()
    try:
        dispatcher = dispatcher_for(state_over(store, discovery_sources={"proxmox": reader}))
    finally:
        await store.close()

    runner = dispatcher.runner_for(TOPOLOGY_DISCOVERY_JOB_KIND)
    assert isinstance(runner, TopologyDiscoveryRunner)
    assert dict(runner.readers) == {"proxmox": reader}


async def test_an_unconfigured_sync_source_is_a_lookup_failure_not_a_quiet_success() -> None:
    store = FakePersistence()
    try:
        runner = dispatcher_for(state_over(store)).runner_for(KNOWLEDGE_SYNC_JOB_KIND)
        with pytest.raises(UnknownSource):
            await runner.run(context(KNOWLEDGE_SYNC_JOB_KIND, source="confluence"))
    finally:
        await store.close()


# --- The other half: what the sweep leaves in the graph ------------------------


@dataclass
class OneNodeAndItsGuest:
    """A source reporting a hypervisor and one virtual machine on it, once.

    Real enough to be swept: the reconciliation derives both identities and the
    parentage from what is reported here, and the graph is written from what was
    stored rather than from this page.
    """

    calls: list[DiscoveryMode] = field(default_factory=list)

    @property
    def declaration(self) -> DiscoveryDeclaration:
        """Return what this source says about itself."""
        return DiscoveryDeclaration(
            integration=DISCOVERY_SOURCE, kinds=(KIND_NODE, KIND_VIRTUAL_MACHINE)
        )

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the whole inventory in one complete page."""
        self.calls.append(mode)
        return DiscoveryPage(
            resources=(
                DiscoveredResource(
                    kind=KIND_NODE,
                    native_id="node/pve1",
                    display_name="pve1",
                    provider_status="online",
                    observed_at=EPOCH,
                ),
                DiscoveredResource(
                    kind=KIND_VIRTUAL_MACHINE,
                    native_id="vm/101",
                    display_name="checkout",
                    parent_native_id="node/pve1",
                    provider_status="running",
                    observed_at=EPOCH,
                ),
            ),
            complete=True,
        )


async def test_a_swept_resource_reaches_the_graph_the_topology_read_traverses() -> None:
    """The two halves meet: the scheduler's sweep writes what the capability reads.

    A bound topology source over a graph nothing populates answers "no
    dependents" for every service in the estate, which is the sentence the
    capability exists to avoid producing. This is the path from the serving
    composition root that stops that being true — dispatched by kind, exactly as
    a claimed job arrives.
    """
    store = FakePersistence()
    reader = OneNodeAndItsGuest()
    host = derive_resource_id(source=DISCOVERY_SOURCE, native_id="node/pve1")
    guest = derive_resource_id(source=DISCOVERY_SOURCE, native_id="vm/101")
    try:
        async with store.begin_system() as system:
            await system.orgs.create_organisation(ORG, "Acme")

        dispatcher = dispatcher_for(state_over(store, discovery_sources={DISCOVERY_SOURCE: reader}))
        result = await dispatcher.dispatch(
            context(ESTATE_DISCOVERY_JOB_KIND, source=DISCOVERY_SOURCE)
        )

        answer = await TopologyQueries(gateway=store, scope=TenantScope(org_id=ORG)).query(host)
    finally:
        await store.close()

    assert result.ran, result.failure
    assert result.record["discovered"] == 2
    assert answer.searched
    assert answer.dependents.names() == (guest,)
