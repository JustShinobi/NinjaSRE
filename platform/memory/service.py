"""The composition root: one object a deployment holds, four collaborators inside it.

Guidance, recall, and finalisation are three modules that have to agree about
four things — the policy, the embedder, the tenant, and the run's recall ledger.
Wiring them separately at each call site is how a deployment ends up with recall
reading one team's corpus and finalisation writing another's, or with an ablation
that switched reading off in the retriever and left the guidance paragraph in the
prompt telling the agent to search a memory it is not allowed to search.

So they are constructed together, from one policy and one scope, and ``install``
attaches both hooks to a loop in one call.

The ledger is shared deliberately. ``MemoryRetriever`` writes to it during the
run and ``MemoryLifecycle`` reads it at the end to mark which recalls the answer
actually used — two halves of FR-022 that only work if they are looking at the
same object.

One service belongs to one run. It holds run-scoped state (the ledger, and the
set of conversations already finalised), and sharing one across concurrent
investigations would have them recording each other's recalls.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.agent.hooks.registry import HookRegistry
from core.llm.types import LLMClient
from platform.guardrails.engine import GuardrailEngine
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import Embedder
from platform.memory.extraction import EpisodeExtractor
from platform.memory.guidance import MemoryGuidance
from platform.memory.lifecycle import MemoryLifecycle
from platform.memory.models import now as _utc_now
from platform.memory.policy import MemoryPolicy
from platform.memory.retrieval import MemoryRetriever, RecallLedger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


class MemoryService:
    """Everything one run needs from episodic memory, wired consistently."""

    __slots__ = ("_guidance", "_ledger", "_lifecycle", "_policy", "_retriever", "_scope")

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        scope: TenantScope,
        llm: LLMClient,
        embedder: Embedder | None = None,
        policy: MemoryPolicy | None = None,
        engine: GuardrailEngine | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        resolved_embedder: Embedder = embedder if embedder is not None else LocalEmbedder()
        self._policy = policy if policy is not None else MemoryPolicy()
        self._scope = scope
        self._ledger = RecallLedger()

        self._retriever = MemoryRetriever(
            gateway=gateway,
            scope=scope,
            embedder=resolved_embedder,
            policy=self._policy,
            ledger=self._ledger,
            clock=clock,
        )
        self._lifecycle = MemoryLifecycle(
            gateway=gateway,
            scope=scope,
            embedder=resolved_embedder,
            extractor=EpisodeExtractor(llm=llm),
            policy=self._policy,
            engine=engine,
            ledger=self._ledger,
            clock=clock,
        )
        self._guidance = MemoryGuidance(policy=self._policy)

    # -- the pieces ------------------------------------------------------------

    @property
    def policy(self) -> MemoryPolicy:
        """Return the switches this service was built with."""
        return self._policy

    @property
    def scope(self) -> TenantScope:
        """Return the organisation and team this service reads and writes under."""
        return self._scope

    @property
    def ledger(self) -> RecallLedger:
        """Return the run's recall ledger, which both halves of FR-022 share."""
        return self._ledger

    @property
    def retriever(self) -> MemoryRetriever:
        """Return the recall path the ``memory-search`` capability calls."""
        return self._retriever

    @property
    def lifecycle(self) -> MemoryLifecycle:
        """Return the finalisation hook."""
        return self._lifecycle

    @property
    def guidance(self) -> MemoryGuidance:
        """Return the root-prompt guidance hook."""
        return self._guidance

    # -- wiring ----------------------------------------------------------------

    def install(self, hooks: HookRegistry) -> MemoryService:
        """Attach whichever hooks this policy calls for, and return this service.

        A disabled switch means the hook is *not registered*, not that it is
        registered and returns early. "Memory off" has to be the same code path a
        deployment without memory takes, or the baseline the ablation compares
        against is a run with two extra hooks in its dispatch order.
        """
        if self._policy.read_enabled:
            self._guidance.register(hooks)
        if self._policy.write_enabled:
            self._lifecycle.register(hooks)
        return self

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about memory.

        The configuration and what happened, kept apart. "Recall was off" and
        "recall found nothing" are different facts, and an ablation table that
        could not tell them apart would be unreadable.
        """
        return {**self._policy.trace_summary(), **self._ledger.trace_summary()}


__all__ = ["MemoryService"]
