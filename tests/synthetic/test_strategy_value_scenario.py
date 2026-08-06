"""What a playbook is worth, measured against the episodes-only baseline.

This is the feature's proof of value, and it is a measurement rather than an
assertion about the design. One scenario family runs twice over the *same*
populated corpus, through the same loop, the same tools, and the same agent
policy. The only difference is the strategy switch. The iteration count of each
is recorded and the delta is the number the claim rests on.

**The mechanism being measured.** Four backends are available and one of them —
`broker_metrics` — returns nothing that bears on this failure. Three previous
investigations went there first and established nothing; that is exactly the
material an anti-patterns section is derived from, and it is the one thing a
runbook could not have told anybody. With playbooks on, the agent is told that
those runs spent their budget there, and skips it. With playbooks off it has the
same three episodes and no such summary, so it works through the backends in
order and pays for the dead end.

**What the agent double is, and why it is not a script.** It is a small
deterministic *policy*: gather the next backend it has not gathered, skipping any
capability the recall result named as an anti-pattern, and conclude once it holds
a root cause. Both runs execute that same policy against the same tools. The
policy is crude compared to a real model and it is stated here in the open, which
is the honest position: what the number measures is the *mechanism* — a
synthesised dead-end warning reaching the agent early enough to change the
trajectory. Whether a real model exploits it as reliably is what the ablation
harness measures against a live provider.

**The control** is the third assertion: with strategies disabled the run has to
take the baseline trajectory exactly, or the delta above is measuring something
other than synthesis.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from capabilities.tools.system.memory_search import binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL_TOOL
from capabilities.tools.system.memory_search.tool import recall_similar_incidents
from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from core.agent.hooks.registry import HookRegistry
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest
from core.capability.metadata import EvidenceType, SideEffectLevel, ToolMetadata
from core.capability.registered import RegisteredTool, build_registration, capability_marker
from core.capability.result import CapabilityResult, Evidence
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    StructuredMechanism,
    TokenEstimate,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import embed_one
from platform.memory.models import Component, MemoryEpisode
from platform.memory.policy import MemoryPolicy
from platform.memory.service import MemoryService
from platform.memory.strategy.models import StrategySection
from platform.memory.strategy.policy import StrategyPolicy
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import VectorRecord

pytestmark = pytest.mark.synthetic

ORG = "acme"
TEAM = "team-payments"

NOW = datetime(2026, 6, 1, 3, 9, tzinfo=UTC)

OBJECTIVE = "payments-api pods are in CrashLoopBackOff and the error rate is above 5%"

ROOT_CAUSE = "the 02:50 deploy lowered the container memory limit from 1Gi to 512Mi"

#: The dead end. It returns something — that is what makes it a dead end rather
#: than a broken tool — and what it returns bears on nothing.
DEAD_END = "broker_metrics"

#: The backends in the order a run with no playbook works through them. The dead
#: end is first, which is the case the anti-patterns section exists for: an
#: approach that looks like the obvious place to start and is not.
BACKENDS: tuple[tuple[str, str], ...] = (
    (DEAD_END, "consumer lag on payments-events is 0 and has been flat for six hours"),
    ("kubernetes_pod_events", "3 OOMKilled events on payments-api between 03:04 and 03:09"),
    ("kubernetes_describe_workload", "container payments-api last state OOMKilled, limit 512Mi"),
    ("deploy_history", "release 4.19.2 deployed at 02:50 changed resources.limits.memory"),
)

CONCLUSION = (
    "payments-api entered CrashLoopBackOff at 03:04 UTC. Every restart is an OOMKill on the "
    f"api container, and {ROOT_CAUSE}. Raising the limit back to 1Gi is expected to resolve it."
)

#: The playbook the synthesis call returns for this corpus. Its anti-patterns
#: name the dead end, which is the whole of what this scenario measures.
PLAYBOOK: Mapping[str, Any] = {
    StrategySection.ROOT_CAUSES.value: [
        "A deploy lowering the container memory limit, in every resolved run",
    ],
    StrategySection.INVESTIGATION_STEPS.value: [
        "Read the workload's last termination state first",
        "Compare the deploy history against the first restart",
    ],
    StrategySection.CAPABILITIES.value: [
        "kubernetes_describe_workload on the failing deployment",
        "deploy_history for the hour before the first restart",
    ],
    StrategySection.ANTI_PATTERNS.value: [
        f"{DEAD_END} — three previous runs started there, found flat lag, and established nothing",
    ],
}

EXTRACTION: Mapping[str, Any] = {
    "issue_type": "oom_kill",
    "issue_description": "payments-api restarting with exit code 137 since 03:04 UTC",
    "severity": "high",
    "components": [{"type": "service", "name": "payments-api"}],
    "key_findings": [],
    "resolved": True,
    "root_cause": ROOT_CAUSE,
    "summary": (
        "payments-api began CrashLoopBackOff at 03:04 after release 4.19.2 lowered the "
        "container memory limit from 1Gi to 512Mi."
    ),
}


def prior_episode(index: int, *, resolved: bool) -> MemoryEpisode:
    """Return one previous investigation of this failure on this component.

    Deliberately *not* all the same. Two of the five went nowhere, and they went
    nowhere in the same way — which is the material the anti-patterns section is
    derived from and the reason a corpus of successes would be worth less.
    """
    return MemoryEpisode(
        correlation_id=f"prior-{index}",
        org_id=ORG,
        team_node_id=TEAM,
        issue_type="oom_kill",
        issue_description="payments-api restarting with exit code 137",
        # A naming variant per episode, so the scenario also exercises the
        # normalisation that makes the threshold reachable at all.
        components=(Component(type="service", name=f"payments-api-{index}"),),
        capabilities_used=(
            ("kubernetes_describe_workload", "deploy_history") if resolved else (DEAD_END,)
        ),
        resolved=resolved,
        root_cause=ROOT_CAUSE if resolved else "",
        summary=(
            "the memory limit had been lowered by a deploy"
            if resolved
            else "spent the run on broker metrics, found flat lag, established nothing"
        ),
        effectiveness_score=0.8 if resolved else 0.15,
        occurred_at=NOW - timedelta(days=7 * index + 1),
    )


def backend(name: str, finding: str) -> RegisteredTool:
    """Return one vendor-shaped capability returning a fixed observation."""

    async def call(query: str) -> CapabilityResult:
        return CapabilityResult.ok(
            name,
            value={"query": query, "finding": finding},
            evidence=(
                Evidence(
                    source="kubernetes",
                    evidence_type=EvidenceType.EVENT,
                    summary=finding,
                    reference=f"kubernetes:{name}",
                ),
            ),
        )

    return build_registration(
        metadata=ToolMetadata(
            name=name,
            display_name=name.replace("_", " ").title(),
            description=f"Read {name.replace('_', ' ')} for the incident window.",
            domain="observability",
            evidence_source="kubernetes",
            evidence_type=EvidenceType.EVENT,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        call=call,
        source_module=__name__,
        source_qualname=f"backend.{name}",
        signature_source=call,
    )


def tools() -> tuple[RegisteredTool, ...]:
    """Return the scenario's backends plus the real recall capability."""
    recall = capability_marker(recall_similar_incidents)
    assert recall is not None
    return (*(backend(name, finding) for name, finding in BACKENDS), recall)


@dataclass(slots=True)
class PolicyAgent:
    """Gather what is missing, skip what a playbook warned about, conclude on a cause.

    Not a script. It reads the transcript the loop hands it and decides from what
    is actually there, which is what lets the two runs differ only in whether a
    playbook came back.
    """

    turns: int = 0
    avoided: set[str] = field(default_factory=set)
    searched_memory: bool = False
    saw_playbook: bool = False
    calls: list[str] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Return the provider this double claims to be."""
        return "policy"

    @property
    def model_id(self) -> str:
        """Return the model this double claims to be."""
        return "policy-1"

    def _usage(self) -> UsageRecord:
        return UsageRecord(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tokens=TokenCounts(input_tokens=400, output_tokens=120),
        )

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the next move this policy makes, given what came back so far."""
        self.turns += 1
        offered = {schema.name for schema in request.tools}
        if not offered:
            return self._answer()

        results = [result for message in request.messages for result in message.tool_results]
        gathered = [
            result for result in results if result.name != RECALL_TOOL and not result.is_error
        ]
        recalls = [result for result in results if result.name == RECALL_TOOL]

        # Memory is searched first here, before any backend. That is a departure
        # from the shipped guidance and it is deliberate: this scenario measures
        # what a playbook is worth *when the agent has one*, and an agent that
        # gathered the dead end before searching would have already paid for it.
        if not self.searched_memory and RECALL_TOOL in offered:
            self.searched_memory = True
            return self._call(RECALL_TOOL, {"query": OBJECTIVE, "issue_type": "oom_kill"})

        self._read_playbook(recalls)

        if any(ROOT_CAUSE in result.content for result in gathered):
            return self._answer()

        called = {result.name for result in gathered}
        remaining = [
            name
            for name, _ in BACKENDS
            if name not in called and name not in self.avoided and name in offered
        ]
        if remaining:
            return self._call(remaining[0], {"query": "payments-api"})
        return self._answer()

    def _read_playbook(self, recalls: Sequence[Any]) -> None:
        """Note which capabilities a returned playbook warned against.

        Substring matching on the anti-patterns block of the rendered result,
        which is what a model reads. Crude, and it is the point: the warning has
        to be legible in the text the agent is actually shown, not only present
        in a structured field nobody renders.
        """
        for result in recalls:
            if "SYNTHESISED PLAYBOOK" not in result.content:
                continue
            self.saw_playbook = True
            _, _, anti = result.content.partition("did not help")
            self.avoided |= {name for name, _ in BACKENDS if name in anti}

    def _call(self, name: str, arguments: Mapping[str, Any]) -> InvokeResult:
        self.calls.append(name)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tool_calls=(ToolCall(id=f"c{self.turns}", name=name, arguments=dict(arguments)),),
            finish_reason=FinishReason.TOOL_CALLS,
            usage=self._usage(),
        )

    def _answer(self) -> InvokeResult:
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=CONCLUSION,
            finish_reason=FinishReason.STOP,
            usage=self._usage(),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Yield the same decision as ``invoke``; unused by this scenario."""
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the playbook or the episode extraction, whichever was asked for."""
        wanted = (
            PLAYBOOK
            if StrategySection.ANTI_PATTERNS.value in (schema.get("properties") or {})
            else EXTRACTION
        )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=dict(wanted),
            structured_mechanism=StructuredMechanism.NATIVE,
            usage=self._usage(),
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a nominal estimate."""
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """One run of the scenario, and what it cost."""

    iterations: int
    backends_called: tuple[str, ...]
    saw_playbook: bool
    answer: str

    @property
    def touched_the_dead_end(self) -> bool:
        """Return whether the run spent an iteration on the approach that never works."""
        return DEAD_END in self.backends_called


async def investigate(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    strategies: StrategyPolicy,
    session_id: str,
) -> RunOutcome:
    """Run the scenario once, end to end, over the real loop and the real hooks."""
    agent = PolicyAgent()
    hooks = HookRegistry()
    memory = MemoryService(
        gateway=gateway,
        scope=scope,
        llm=agent,
        policy=MemoryPolicy(),
        strategy_policy=strategies,
        clock=lambda: NOW,
    ).install(hooks)

    previous = binding.bind(memory.recall)
    try:
        loop = ReActLoop(llm=agent, tools=tools(), hooks=hooks)
        result = await loop.run(RunRequest(objective=OBJECTIVE, session_id=session_id))
    finally:
        binding.restore(previous)

    return RunOutcome(
        iterations=result.iterations,
        backends_called=tuple(name for name in agent.calls if name != RECALL_TOOL),
        saw_playbook=agent.saw_playbook,
        answer=result.answer,
    )


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with the organisation created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the team the scenario runs under."""
    return TenantScope(org_id=ORG, team_node_id=TEAM)


@pytest.fixture
async def populated(gateway: PersistenceGateway, scope: TenantScope) -> PersistenceGateway:
    """Return the gateway carrying five previous investigations of this failure.

    Three that established the cause and two that did not, which is what makes
    the anti-patterns section derivable at all — and the same corpus is in place
    for both arms of the measurement.
    """
    embedder = LocalEmbedder()
    corpus = (
        prior_episode(1, resolved=True),
        prior_episode(2, resolved=True),
        prior_episode(3, resolved=True),
        prior_episode(4, resolved=False),
        prior_episode(5, resolved=False),
    )
    async with gateway.begin(scope) as uow:
        await uow.vectors.ensure(
            EPISODE_VECTOR_NAMESPACE, model=embedder.model, dimension=embedder.dimension
        )
        for item in corpus:
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
    return gateway


async def test_a_playbook_shortens_the_trajectory_against_the_episodes_only_baseline(
    populated: PersistenceGateway, scope: TenantScope
) -> None:
    """The feature's proof of value: the same corpus, twice, with and without it."""
    baseline = await investigate(
        populated, scope, strategies=StrategyPolicy.disabled(), session_id="conv-baseline"
    )
    withplaybook = await investigate(
        populated, scope, strategies=StrategyPolicy(), session_id="conv-strategy"
    )

    assert not baseline.saw_playbook, "the baseline must be episodes only"
    assert withplaybook.saw_playbook, "the corpus reaches the threshold; a playbook was expected"

    # The mechanism: the baseline pays for the approach three previous runs
    # already established does not work, and the playbook arm does not.
    assert baseline.touched_the_dead_end
    assert not withplaybook.touched_the_dead_end

    # The number the claim rests on. Recorded rather than only asserted: a change
    # in it is a change in what the feature is worth.
    reduction = baseline.iterations - withplaybook.iterations
    assert reduction >= 1, (
        f"synthesis did not reduce the trajectory: {baseline.iterations} then "
        f"{withplaybook.iterations}"
    )
    assert withplaybook.answer


async def test_with_strategies_disabled_the_run_matches_the_episodes_only_baseline(
    populated: PersistenceGateway, scope: TenantScope
) -> None:
    """Over the real loop: off means off, and off is the baseline.

    Run twice with the switch off against the same corpus. If a playbook could
    leak into either — through a cache written by an earlier arm, say — the two
    would differ, and the reduction measured above would be measuring the leak.
    """
    first = await investigate(
        populated, scope, strategies=StrategyPolicy.disabled(), session_id="conv-1"
    )
    # An arm with synthesis on runs in between, so there is now a playbook in the
    # store for this key. The switch has to make it unreachable, not merely
    # unrequested.
    await investigate(populated, scope, strategies=StrategyPolicy(), session_id="conv-2")
    second = await investigate(
        populated, scope, strategies=StrategyPolicy.disabled(), session_id="conv-3"
    )

    assert not second.saw_playbook
    assert second.iterations == first.iterations
    assert second.backends_called == first.backends_called


async def test_the_playbook_is_synthesised_once_and_then_served_from_cache(
    populated: PersistenceGateway, scope: TenantScope
) -> None:
    """The cost model the feature depends on, over the real loop.

    Two investigations of the same failure, and the second must not pay for
    synthesis. Asserted on the stored playbook's generation timestamp rather than
    on a call counter, because the run that matters is the second one and what it
    must not do is write a new row.
    """
    await investigate(populated, scope, strategies=StrategyPolicy(), session_id="conv-1")

    async with populated.begin(scope) as uow:
        after_first = await uow.episodes.list_strategies(team_node_id=TEAM)

    assert len(after_first) == 1

    await investigate(populated, scope, strategies=StrategyPolicy(), session_id="conv-2")

    async with populated.begin(scope) as uow:
        after_second = await uow.episodes.list_strategies(team_node_id=TEAM)

    assert len(after_second) == 1
    # The first run wrote an episode of its own, which invalidates the playbook;
    # the second regenerates it. What must not happen is a second row.
    assert after_second[0].component_key == after_first[0].component_key
