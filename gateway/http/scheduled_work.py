"""Wiring the job kinds this deployment can run, from what it was given.

The scheduler dispatches by kind and the runners do the work, but neither can
build the other's collaborators: a document sync needs an ingestor, which needs
an embedder, a guardrail engine and a store, and all three are deployment
concerns. This is where they meet — the same composition root that already
answers "what does this deployment run on".

**Every shipped kind is registered, even with nothing wired for it.** A
deployment that has configured no wiki still gets a ``knowledge.sync`` runner,
and a job naming a source then fails with *"no sync source named 'wiki' is
configured; this deployment can sync: nothing"*. Skipping the registration would
have produced *"no runner is registered for kind 'knowledge.sync'"* instead,
which reads as a hole in the build rather than as configuration that has drifted
— and sends the operator to the wrong place.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from config.constants.estate import ESTATE_DISCOVERY_JOB_KIND
from config.constants.knowledge import (
    CORPUS_SYNC_JOB_KIND,
    KNOWLEDGE_SYNC_JOB_KIND,
    TOPOLOGY_DISCOVERY_JOB_KIND,
)
from config.constants.observation import OBSERVATION_TICK_JOB_KIND
from gateway.http.observation_job import ObservationTickJobRunner
from gateway.http.state import GatewayState
from platform.estate.discovery.enriched import EnrichingSweeper
from platform.estate.discovery.runner import TopologyDiscoveryRunner
from platform.estate.discovery.sweep import EstateSweeper
from platform.knowledge.base.sync.corpus_run import CorpusSync
from platform.knowledge.base.sync.port import KnowledgeSync
from platform.knowledge.base.sync.runner import CorpusSyncRunner, KnowledgeSyncRunner
from platform.knowledge.service import KnowledgeService
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope
from platform.scheduler.dispatch import JobKindDispatcher, ScheduledJobWorker


def _sync_for(state: GatewayState, scope: TenantScope) -> KnowledgeSync:
    """Return the document sync for one tenant, over this deployment's stores.

    Built per run rather than held: the sync is scoped to a tenant, and one
    worker claims for every tenant in the deployment.
    """
    service = KnowledgeService(gateway=state.gateway, scope=scope, engine=state.guardrails)
    return KnowledgeSync(ingestor=service.ingestor, scope=scope)


logger = get_logger(__name__)


def dispatcher_for(state: GatewayState) -> JobKindDispatcher:
    """Return the dispatcher holding every job kind this build can run."""
    dispatcher = JobKindDispatcher()
    dispatcher.register(
        KNOWLEDGE_SYNC_JOB_KIND,
        KnowledgeSyncRunner(
            sources=dict(state.knowledge_sources),
            sync_for=lambda scope: _sync_for(state, scope),
        ),
    )
    dispatcher.register(
        CORPUS_SYNC_JOB_KIND,
        CorpusSyncRunner(
            sources=dict(state.corpus_sources),
            corpus_for=lambda scope: CorpusSync(
                ingestor_sync=_sync_for(state, scope),
                gateway=state.gateway,
                scope=scope,
            ),
        ),
    )
    # One runner, two kinds, because two schedulers write them: the estate's own
    # registration writes estate.discovery and the knowledge graph's writes
    # topology.discovery. Both mean "sweep this source", and a kind nothing
    # dispatches is a job that is claimed, found unrunnable and rescheduled for
    # ever without a line saying so.
    sweep = TopologyDiscoveryRunner(
        readers=dict(state.discovery_sources),
        # What the operator declared about the estate. Composed at boot and
        # held here, because a plan nobody hands the runner leaves every
        # resource without a criticality, a tier, a domain or an owner — the
        # four annotations the whole ingestion exists to produce.
        plans=dict(state.enrichment_plans),
        sweeper=EnrichingSweeper(
            sweeper=EstateSweeper(gateway=state.gateway, kinds=state.estate_kinds)
        ),
    )
    dispatcher.register(TOPOLOGY_DISCOVERY_JOB_KIND, sweep)
    dispatcher.register(ESTATE_DISCOVERY_JOB_KIND, sweep)
    dispatcher.register(OBSERVATION_TICK_JOB_KIND, ObservationTickJobRunner(state=state))
    return dispatcher


async def run_scheduler(worker: Any, *, interval_seconds: float, stop: asyncio.Event) -> None:
    """Claim and run everything due, on an interval, until ``stop`` is set.

    The piece that was missing. A job registered through a route is a row with
    a due time, and a due time nobody comes round for is a job that never runs
    — which is what left an estate empty on a deployment that had been pointed
    at its own cluster.

    **One bad tick does not end the loop.** A store that goes away for a moment
    must not take every recurring job with it; the alternative is a deployment
    that looks like one which scheduled nothing, with no line saying otherwise.

    **Stopping is immediate.** The wait is on the event rather than on the
    clock, so a restart does not pause for as long as the slowest schedule.
    """
    while not stop.is_set():
        try:
            results = await worker.tick()
        except asyncio.CancelledError:
            raise
        except Exception as failed:  # noqa: BLE001 — one tick must not end the loop
            logger.warning("scheduler.tick_failed", error=str(failed))
        else:
            if results:
                logger.info("scheduler.tick", ran=len(results))
        if interval_seconds <= 0:
            # Yield, so a caller driving this in a test is not starved.
            await asyncio.sleep(0)
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)


def worker_for(state: GatewayState, *, worker_id: str = "gateway") -> ScheduledJobWorker:
    """Return the worker that claims due jobs and runs them by kind."""
    return ScheduledJobWorker(
        gateway=state.gateway,
        dispatcher=dispatcher_for(state),
        worker_id=worker_id,
    )


__all__ = ["dispatcher_for", "worker_for"]
