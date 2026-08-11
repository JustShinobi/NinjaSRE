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

from datetime import UTC, datetime

import pytest

from config.constants.knowledge import (
    CORPUS_SYNC_JOB_KIND,
    KNOWLEDGE_SYNC_JOB_KIND,
    TOPOLOGY_DISCOVERY_JOB_KIND,
)
from gateway.http.scheduled_work import dispatcher_for
from gateway.http.state import GatewayState
from platform.estate.discovery.runner import TopologyDiscoveryRunner
from platform.knowledge.base.sync.runner import UnknownSource
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import JobClaim, ScheduledJob, TenantScope
from platform.scheduler.dispatch import JobContext

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)


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
