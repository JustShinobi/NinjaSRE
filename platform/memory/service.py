"""The composition root: one object a deployment holds, and the collaborators inside it.

Guidance, recall, synthesis, and finalisation are four modules that have to agree
about five things — the policies, the embedder, the tenant, the normaliser, and
the run's recall ledger. Wiring them separately at each call site is how a
deployment ends up with recall reading one team's corpus and finalisation writing
another's, or with an ablation that switched reading off in the retriever and left
the guidance paragraph in the prompt telling the agent to search a memory it is
not allowed to search.

So they are constructed together, from one pair of policies and one scope, and
``install`` attaches the hooks to a loop in one call.

The ledger is shared deliberately. ``MemoryRetriever`` writes to it during the
run and ``MemoryLifecycle`` reads it at the end to mark which recalls the answer
actually used — two halves of one requirement that only work if they are looking
at the same object.

The **normaliser** is shared for the same kind of reason, and it is the sharper
version of it. Synthesis keys a playbook on a normalised component; the episode
write invalidates a playbook by normalising the same component. Two normalisers
that disagreed would produce a cache nothing ever invalidates, and the failure
mode is silent — a playbook that is merely out of date. One object, constructed
here, handed to both.

One service belongs to one run. It holds run-scoped state (the ledger, the set of
conversations already finalised, and the per-key synthesis locks), and sharing one
across concurrent investigations would have them recording each other's recalls.
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
from platform.memory.strategy.cache import StrategyCache
from platform.memory.strategy.generator import StrategyGenerator
from platform.memory.strategy.invalidation import StrategyInvalidator
from platform.memory.strategy.normalisation import DEFAULT_NORMALISER, ComponentNormaliser
from platform.memory.strategy.policy import StrategyPolicy
from platform.memory.strategy.service import StrategyDirectory, StrategyRecall
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


class MemoryService:
    """Everything one run needs from episodic memory, wired consistently."""

    __slots__ = (
        "_cache",
        "_directory",
        "_guidance",
        "_ledger",
        "_lifecycle",
        "_normaliser",
        "_policy",
        "_recall",
        "_retriever",
        "_scope",
        "_strategy_policy",
    )

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        scope: TenantScope,
        llm: LLMClient,
        embedder: Embedder | None = None,
        policy: MemoryPolicy | None = None,
        strategy_policy: StrategyPolicy | None = None,
        normaliser: ComponentNormaliser | None = None,
        engine: GuardrailEngine | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        resolved_embedder: Embedder = embedder if embedder is not None else LocalEmbedder()
        self._policy = policy if policy is not None else MemoryPolicy()
        self._strategy_policy = strategy_policy if strategy_policy is not None else StrategyPolicy()
        self._normaliser = normaliser if normaliser is not None else DEFAULT_NORMALISER
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
        self._cache = StrategyCache(
            gateway=gateway,
            scope=scope,
            generator=StrategyGenerator(llm=llm, engine=engine, clock=clock),
            policy=self._strategy_policy,
            clock=clock,
        )
        self._recall = StrategyRecall(
            retriever=self._retriever,
            cache=self._cache,
            normaliser=self._normaliser,
            policy=self._strategy_policy,
            ledger=self._ledger,
            clock=clock,
        )
        self._directory = StrategyDirectory(
            gateway=gateway, scope=scope, cache=self._cache, clock=clock
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
            # Invalidation is not gated on the strategy switch. A run with
            # playbooks disabled still writes episodes, and a corpus that moved
            # while nobody was reading it must not leave a stale playbook looking
            # current the moment somebody switches the feature back on.
            invalidator=StrategyInvalidator(normaliser=self._normaliser),
        )
        self._guidance = MemoryGuidance(policy=self._policy)

    # -- the pieces ------------------------------------------------------------

    @property
    def policy(self) -> MemoryPolicy:
        """Return the episodic switches this service was built with."""
        return self._policy

    @property
    def strategy_policy(self) -> StrategyPolicy:
        """Return the synthesis switch this service was built with."""
        return self._strategy_policy

    @property
    def scope(self) -> TenantScope:
        """Return the organisation and team this service reads and writes under."""
        return self._scope

    @property
    def ledger(self) -> RecallLedger:
        """Return the run's recall ledger, which both halves of the trace share."""
        return self._ledger

    @property
    def retriever(self) -> MemoryRetriever:
        """Return the bare episode recall path, without playbooks attached."""
        return self._retriever

    @property
    def recall(self) -> StrategyRecall:
        """Return the recall path the ``memory-search`` capability binds.

        Episodes *and* the playbooks they imply, because the agent should not have
        to decide to ask for a playbook before it knows one exists.
        """
        return self._recall

    @property
    def strategies(self) -> StrategyCache:
        """Return the synthesis cache."""
        return self._cache

    @property
    def directory(self) -> StrategyDirectory:
        """Return the operator's read and write access to this team's playbooks."""
        return self._directory

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
        "recall found nothing" are different facts, and so are "playbooks were
        off" and "no playbook existed yet"; an ablation table that could not tell
        either pair apart would be unreadable.
        """
        return {
            **self._policy.trace_summary(),
            **self._strategy_policy.trace_summary(),
            **self._ledger.trace_summary(),
        }


__all__ = ["MemoryService"]
