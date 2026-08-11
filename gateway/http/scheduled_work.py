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

from config.constants.knowledge import (
    CORPUS_SYNC_JOB_KIND,
    KNOWLEDGE_SYNC_JOB_KIND,
    TOPOLOGY_DISCOVERY_JOB_KIND,
)
from gateway.http.state import GatewayState
from platform.estate.discovery.enriched import EnrichingSweeper
from platform.estate.discovery.runner import TopologyDiscoveryRunner
from platform.estate.discovery.sweep import EstateSweeper
from platform.knowledge.base.sync.corpus_run import CorpusSync
from platform.knowledge.base.sync.port import KnowledgeSync
from platform.knowledge.base.sync.runner import CorpusSyncRunner, KnowledgeSyncRunner
from platform.knowledge.service import KnowledgeService
from platform.persistence.ports.transaction import TenantScope
from platform.scheduler.dispatch import JobKindDispatcher, ScheduledJobWorker


def _sync_for(state: GatewayState, scope: TenantScope) -> KnowledgeSync:
    """Return the document sync for one tenant, over this deployment's stores.

    Built per run rather than held: the sync is scoped to a tenant, and one
    worker claims for every tenant in the deployment.
    """
    service = KnowledgeService(gateway=state.gateway, scope=scope, engine=state.guardrails)
    return KnowledgeSync(ingestor=service.ingestor, scope=scope)


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
    dispatcher.register(
        TOPOLOGY_DISCOVERY_JOB_KIND,
        TopologyDiscoveryRunner(
            readers=dict(state.discovery_sources),
            sweeper=EnrichingSweeper(
                sweeper=EstateSweeper(gateway=state.gateway, kinds=state.estate_kinds)
            ),
        ),
    )
    return dispatcher


def worker_for(state: GatewayState, *, worker_id: str = "gateway") -> ScheduledJobWorker:
    """Return the worker that claims due jobs and runs them by kind."""
    return ScheduledJobWorker(
        gateway=state.gateway,
        dispatcher=dispatcher_for(state),
        worker_id=worker_id,
    )


__all__ = ["dispatcher_for", "worker_for"]
