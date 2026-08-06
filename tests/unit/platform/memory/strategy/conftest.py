"""Shared fixtures for the strategy suite.

Built on the episodic memory suite's fixtures rather than beside them — same
gateway, same two organisations, same two teams, same fixed clock — because
almost every assertion here is about the relationship between an episode and a
playbook, and two corpora would make that relationship a coincidence.

The one addition is ``CountingLLM``. Two of this suite's claims are counting
arguments: a cache hit must perform *no* call, and N concurrent requests must
perform *one*. Neither can be asserted against a stub that does not count, and
neither is convincingly asserted by inspecting a log line.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from core.llm.types import InvokeRequest, InvokeResult, StreamEvent, TokenEstimate
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import embed_one
from platform.memory.models import Component, MemoryEpisode, ScoredEpisode
from platform.memory.strategy.cache import StrategyCache
from platform.memory.strategy.generator import StrategyGenerator
from platform.memory.strategy.models import StrategyKey, StrategySection
from platform.memory.strategy.policy import StrategyPolicy
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import VectorRecord
from tests.unit.platform.memory.conftest import at

#: A complete, well-formed synthesis reply. Every string in it is distinctive, so
#: an assertion that a section reached the agent cannot pass by accident.
SYNTHESIS_REPLY: dict[str, Any] = {
    StrategySection.ROOT_CAUSES.value: [
        "A deploy lowering the container memory limit, in 2 of 3 resolved runs",
        "A consumer leaking buffers under partition rebalance, in 1 of 3",
    ],
    StrategySection.INVESTIGATION_STEPS.value: [
        "Read the workload's last termination state before anything else",
        "Compare the deploy history against the first restart",
    ],
    StrategySection.CAPABILITIES.value: [
        "describe_workload on the failing deployment",
        "read_logs scoped to the incident window",
    ],
    StrategySection.ANTI_PATTERNS.value: [
        "Reading broker metrics first — two runs spent their budget there and found nothing",
        "Scaling the deployment out before establishing the cause",
    ],
}


@dataclass(slots=True)
class CountingLLM:
    """An ``LLMClient`` that counts its structured calls and can be made to fail.

    ``delay`` exists for the concurrency test. Without a suspension point inside
    the call, the first caller would finish before the second one started and the
    test would pass against an implementation with no lock in it at all.
    """

    structured: Mapping[str, Any] | None = None
    raises: BaseException | None = None
    failure_message: str = ""
    delay: float = 0.0
    calls: list[InvokeRequest] = field(default_factory=list)

    @property
    def call_count(self) -> int:
        """Return how many structured calls have been made."""
        return len(self.calls)

    @property
    def provider_id(self) -> str:
        """Return the provider this stub claims to be."""
        return "stub"

    @property
    def model_id(self) -> str:
        """Return the model this stub claims to be."""
        return "stub-model"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return an empty successful result."""
        self.calls.append(request)
        return InvokeResult(provider_id=self.provider_id, model_id=self.model_id)

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Never used by synthesis; present so this satisfies the port."""
        raise NotImplementedError("the strategy suite does not stream")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the configured reply, or raise the configured exception."""
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        if self.structured is None:
            from core.llm.failures import FailureClass

            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                partial=True,
                failure=FailureClass.TRANSIENT,
                failure_message=self.failure_message or "the provider was unavailable",
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=self.structured,
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a nominal estimate."""
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


@pytest.fixture
def synthesis_llm() -> CountingLLM:
    """Return an LLM stub primed with a complete synthesis reply."""
    return CountingLLM(structured=dict(SYNTHESIS_REPLY))


def key_for(scope: TenantScope, *, issue_type: str = "oom_kill") -> StrategyKey:
    """Return the key the corpus below synthesises under."""
    return StrategyKey(
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type=issue_type,
        component_key="service:payments",
    )


def episode(
    correlation_id: str,
    scope: TenantScope,
    *,
    issue_type: str = "oom_kill",
    components: tuple[str, ...] = ("service:payments-api",),
    resolved: bool = True,
    effectiveness: float = 0.8,
    age_days: float = 1.0,
    root_cause: str = "the memory limit was lowered by the 02:50 deploy",
    summary: str = "payments-api OOMKilled after a deploy lowered the memory limit",
) -> MemoryEpisode:
    """Return one episode of the corpus under test."""
    return MemoryEpisode(
        correlation_id=correlation_id,
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type=issue_type,
        issue_description="payments-api restarting with exit code 137",
        components=tuple(Component.parse(label) for label in components),
        capabilities_used=("describe_workload", "read_logs"),
        resolved=resolved,
        root_cause=root_cause if resolved else "",
        summary=summary,
        effectiveness_score=effectiveness,
        occurred_at=at(-age_days),
    )


def scored(*episodes: MemoryEpisode) -> tuple[ScoredEpisode, ...]:
    """Return episodes as recall would have ranked them, best first."""
    return tuple(
        ScoredEpisode(episode=item, similarity=0.9, score=0.9 - index / 100)
        for index, item in enumerate(episodes)
    )


async def seed(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    *episodes: MemoryEpisode,
) -> None:
    """Write episodes and their vectors, as finalisation would."""
    async with gateway.begin(scope) as uow:
        await uow.vectors.ensure(
            EPISODE_VECTOR_NAMESPACE, model=embedder.model, dimension=embedder.dimension
        )
        for item in episodes:
            await uow.episodes.save(item.to_stored())
            await uow.vectors.upsert(
                EPISODE_VECTOR_NAMESPACE,
                [
                    VectorRecord(
                        vector_id=item.correlation_id,
                        embedding=await embed_one(embedder, item.embedding_text()),
                        metadata=item.vector_metadata(),
                    )
                ],
            )


def cache_for(
    gateway: PersistenceGateway,
    scope: TenantScope,
    llm: CountingLLM,
    *,
    policy: StrategyPolicy | None = None,
) -> StrategyCache:
    """Return a cache with a fixed clock, so an age check is a constant."""
    return StrategyCache(
        gateway=gateway,
        scope=scope,
        generator=StrategyGenerator(llm=llm, clock=at),
        policy=policy or StrategyPolicy(),
        clock=at,
    )


#: A corpus that reaches the threshold: three runs that found the cause and two
#: that did not. The mixed set is the point — a playbook drawn only from failures
#: cannot show that the anti-patterns section was attributed correctly.
def mixed_corpus(scope: TenantScope) -> tuple[MemoryEpisode, ...]:
    """Return three resolved and two unresolved episodes of the same failure."""
    return (
        episode("ep-resolved-1", scope, age_days=1.0),
        episode("ep-resolved-2", scope, age_days=8.0),
        episode("ep-resolved-3", scope, age_days=15.0),
        episode(
            "ep-unresolved-1",
            scope,
            resolved=False,
            effectiveness=0.2,
            age_days=22.0,
            summary="spent the run reading broker metrics and established nothing",
        ),
        episode(
            "ep-unresolved-2",
            scope,
            resolved=False,
            effectiveness=0.1,
            age_days=29.0,
            summary="scaled the deployment out, restarts continued, no cause found",
        ),
    )
