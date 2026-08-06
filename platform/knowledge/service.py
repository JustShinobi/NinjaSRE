"""The composition root: one object a deployment holds, and the pieces inside it.

Ten collaborators have to agree about four things — the policy, the tenant, the
embedder, and the two ledgers the trace is assembled from. Wiring them separately
at each call site is how a deployment ends up with search reading one team's
corpus and ingestion writing another's, or with an ablation that switched
topology off in the query path and left the guidance paragraph in the prompt
telling the agent to query a graph it is not allowed to query.

So they are constructed together, from one policy and one scope, and ``install``
attaches the guidance hook in one call.

The ledgers are shared deliberately. The queries object and the search object
write to them during the run and ``trace_summary`` reads them at the end — two
halves of one requirement (FR-023) that only work if they are looking at the same
objects.

One service belongs to one run. It holds run-scoped state, and sharing one across
concurrent investigations would have them recording each other's queries.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.agent.hooks.registry import HookRegistry
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.search import KnowledgeLedger, KnowledgeSearch
from platform.knowledge.base.tree import KnowledgeTree
from platform.knowledge.clock import now as _utc_now
from platform.knowledge.guidance import KnowledgeGuidance
from platform.knowledge.policy import KnowledgePolicy
from platform.knowledge.proposals import ProposalQueue
from platform.knowledge.topology.import_ import TopologyImporter
from platform.knowledge.topology.queries import TopologyLedger, TopologyQueries
from platform.knowledge.topology.reconciliation import TopologyReconciler
from platform.knowledge.topology.write import TopologyWriter
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import Embedder
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


class KnowledgeService:
    """Everything one run needs from topology and the knowledge base, wired once."""

    __slots__ = (
        "_guidance",
        "_importer",
        "_ingestor",
        "_knowledge_ledger",
        "_policy",
        "_proposals",
        "_reconciler",
        "_scope",
        "_search",
        "_topology",
        "_topology_ledger",
        "_tree",
        "_writer",
    )

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: Embedder | None = None,
        policy: KnowledgePolicy | None = None,
        engine: GuardrailEngine | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        resolved_embedder: Embedder = embedder if embedder is not None else LocalEmbedder()
        self._policy = policy if policy is not None else KnowledgePolicy()
        self._scope = scope
        self._topology_ledger = TopologyLedger()
        self._knowledge_ledger = KnowledgeLedger()

        self._topology = TopologyQueries(
            gateway=gateway,
            scope=scope,
            policy=self._policy,
            ledger=self._topology_ledger,
            clock=clock,
        )
        self._search = KnowledgeSearch(
            gateway=gateway,
            scope=scope,
            embedder=resolved_embedder,
            policy=self._policy,
            ledger=self._knowledge_ledger,
            clock=clock,
        )
        self._ingestor = KnowledgeIngestor(
            gateway=gateway,
            scope=scope,
            embedder=resolved_embedder,
            engine=engine,
            clock=clock,
        )
        self._proposals = ProposalQueue(
            gateway=gateway,
            scope=scope,
            ingestor=self._ingestor,
            engine=engine,
            clock=clock,
        )
        self._tree = KnowledgeTree(gateway=gateway, scope=scope)
        self._writer = TopologyWriter(gateway=gateway, scope=scope, clock=clock)
        self._importer = TopologyImporter(gateway=gateway, scope=scope, clock=clock)
        self._reconciler = TopologyReconciler(gateway=gateway, scope=scope, clock=clock)
        self._guidance = KnowledgeGuidance(policy=self._policy)

    # -- the pieces ------------------------------------------------------------

    @property
    def policy(self) -> KnowledgePolicy:
        """Return the two switches this service was built with."""
        return self._policy

    @property
    def scope(self) -> TenantScope:
        """Return the organisation and team this service reads and writes under."""
        return self._scope

    @property
    def topology(self) -> TopologyQueries:
        """Return the graph read path the ``topology_query`` capability binds."""
        return self._topology

    @property
    def search(self) -> KnowledgeSearch:
        """Return the read path the ``knowledge_search`` capability binds."""
        return self._search

    @property
    def ingestor(self) -> KnowledgeIngestor:
        """Return the ingestion path an upload or a sync run uses."""
        return self._ingestor

    @property
    def proposals(self) -> ProposalQueue:
        """Return the review queue the ``knowledge_propose`` capability binds."""
        return self._proposals

    @property
    def tree(self) -> KnowledgeTree:
        """Return the operator's listing and hierarchy."""
        return self._tree

    @property
    def writer(self) -> TopologyWriter:
        """Return manual topology entry and annotation."""
        return self._writer

    @property
    def importer(self) -> TopologyImporter:
        """Return the declarative topology import."""
        return self._importer

    @property
    def reconciler(self) -> TopologyReconciler:
        """Return the discovery reconciler."""
        return self._reconciler

    @property
    def guidance(self) -> KnowledgeGuidance:
        """Return the root-prompt guidance hook."""
        return self._guidance

    @property
    def topology_ledger(self) -> TopologyLedger:
        """Return the run's topology query ledger."""
        return self._topology_ledger

    @property
    def knowledge_ledger(self) -> KnowledgeLedger:
        """Return the run's knowledge search ledger."""
        return self._knowledge_ledger

    # -- wiring ----------------------------------------------------------------

    def install(self, hooks: HookRegistry) -> KnowledgeService:
        """Attach the guidance hook if either store is on, and return this service.

        A policy with both switches off registers *nothing*. "Off" has to be the
        same code path a deployment without either store takes, or the baseline
        an ablation compares against is a run with one extra hook in its dispatch
        order — and a trajectory comparison reads that order.
        """
        if self._policy.enabled:
            self._guidance.register(hooks)
        return self

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about both stores.

        The configuration and what happened, kept apart. "Topology was off" and
        "topology held nothing for that service" are different facts, and so are
        "the knowledge base was off" and "nobody has written about this" — an
        ablation table that could not tell either pair apart would be unreadable.
        """
        return {
            **self._policy.trace_summary(),
            **self._topology_ledger.trace_summary(),
            **self._knowledge_ledger.trace_summary(),
        }


__all__ = ["KnowledgeService"]
