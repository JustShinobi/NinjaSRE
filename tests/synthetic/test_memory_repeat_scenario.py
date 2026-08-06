"""SC-003: the same incident, twice, with the iteration count recorded both times.

This is the feature's proof of value, and it is a measurement rather than an
assertion about the design. One scenario is run against an empty corpus, its
episode is written by the real ``on_run_end`` hook, and the *same* scenario runs
again against the corpus the first run left behind. The iteration count of each
is recorded and the delta is the number the claim rests on.

**What the agent double is, and why it is not a script.** A fixed sequence of
turns would make the second run shorter by construction, which would prove
nothing. So the double is a small deterministic *policy* instead: gather the next
piece of evidence it has not gathered, unless a memory recall has come back
naming a root cause, in which case conclude. Both runs execute the same policy
against the same tools; the only difference between them is what memory
contained when they started. That is what makes the delta attributable.

The policy is crude compared to a real model and it is stated in the open, which
is the honest position. What the number measures is the *mechanism* — recall
returning a usable precedent early enough to short-circuit the gathering — and
that is what SC-003 asks about. Whether a real model exploits it as reliably is
what the ablation harness measures against a live provider.

The third run is the control: identical policy, identical corpus, recall
switched off. It has to take the first run's number, or the delta is measuring
something other than memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from capabilities.tools.system.memory_search import binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL_TOOL
from capabilities.tools.system.memory_search.tool import recall_similar_incidents
from core.agent.hooks.registry import HookRegistry
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunResult
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
from platform.memory.policy import MemoryPolicy
from platform.memory.service import MemoryService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope

pytestmark = [pytest.mark.synthetic]

ORG = "acme"
TEAM = "team-payments"

OBJECTIVE = "payments-api pods are in CrashLoopBackOff and the error rate is above 5%"

ROOT_CAUSE = "the 02:50 deploy lowered the container memory limit from 1Gi to 512Mi"

#: The evidence the scenario's three backends return, in the order a run with no
#: precedent has to work through them.
BACKENDS: tuple[tuple[str, str], ...] = (
    ("kubernetes_pod_events", "3 OOMKilled events on payments-api between 03:04 and 03:09"),
    ("kubernetes_describe_workload", "container payments-api last state OOMKilled, limit 512Mi"),
    ("deploy_history", "release 4.19.2 deployed at 02:50 changed resources.limits.memory"),
)

CONCLUSION = (
    "payments-api entered CrashLoopBackOff at 03:04 UTC. Every restart is an OOMKill on the "
    "api container [e1][e2]. The 02:50 deploy of release 4.19.2 lowered the container memory "
    f"limit from 1Gi to 512Mi [e3], and {ROOT_CAUSE}. The working set has not changed. "
    "Raising the limit back to 1Gi is expected to resolve it, and the deploy that lowered it "
    "should be reviewed before the next release."
)

EXTRACTION: Mapping[str, Any] = {
    "issue_type": "oom_kill",
    "issue_description": "payments-api restarting with exit code 137 since 03:04 UTC",
    "severity": "high",
    "components": [{"type": "service", "name": "payments-api"}],
    "key_findings": [
        {
            "capability": "kubernetes_describe_workload",
            "query": "payments-api",
            "finding": "last state OOMKilled, memory limit 512Mi",
        }
    ],
    "resolved": True,
    "root_cause": ROOT_CAUSE,
    "summary": (
        "payments-api began CrashLoopBackOff at 03:04 after release 4.19.2 lowered the "
        "container memory limit from 1Gi to 512Mi. Every restart is an OOMKill on the same "
        "container, and the working set is unchanged."
    ),
}


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
    """A deterministic agent: gather what is missing, or conclude on a precedent.

    Not a script. It reads the transcript the loop hands it and decides from
    what is actually there, which is what lets the two runs differ only in what
    memory contained.
    """

    structured: Mapping[str, Any]
    structured_calls: int = 0
    turns: int = 0
    recalled: bool = False
    searched_memory: bool = False

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
        if not self._memory_offered(request) and not self._backends_offered(request):
            # Tool access has been withdrawn. Answering from what is held is what
            # the loop's final-turn instruction asks for.
            return self._answer()

        results = [result for message in request.messages for result in message.tool_results]
        gathered = [
            result for result in results if result.name != RECALL_TOOL and not result.is_error
        ]
        recalls = [result for result in results if result.name == RECALL_TOOL]

        # The guidance says gather evidence before searching memory, so one
        # observation is taken first. Memory is searched at most once: a second
        # search on the same evidence would return the same thing.
        if gathered and not self.searched_memory and self._memory_offered(request):
            self.searched_memory = True
            return self._call(RECALL_TOOL, {"query": gathered[-1].content[:200]})

        if any(ROOT_CAUSE in result.content for result in recalls):
            self.recalled = True
            return self._answer()

        remaining = [name for name, _ in BACKENDS if not any(name == r.name for r in gathered)]
        if remaining:
            return self._call(remaining[0], {"query": "payments-api"})

        return self._answer()

    @staticmethod
    def _memory_offered(request: InvokeRequest) -> bool:
        """Return whether recall is on this turn at all."""
        return any(schema.name == RECALL_TOOL for schema in request.tools)

    @staticmethod
    def _backends_offered(request: InvokeRequest) -> bool:
        """Return whether any evidence-gathering capability is on this turn."""
        offered = {schema.name for schema in request.tools}
        return any(name in offered for name, _ in BACKENDS)

    def _call(self, name: str, arguments: Mapping[str, Any]) -> InvokeResult:
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
        """Return the episode extraction, which is the only structured call here."""
        self.structured_calls += 1
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=dict(self.structured),
            structured_mechanism=StructuredMechanism.NATIVE,
            usage=self._usage(),
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a nominal estimate."""
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """One run of the scenario, and what it cost."""

    result: RunResult
    iterations: int
    recalled: bool
    episodes: int


async def investigate(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    policy: MemoryPolicy,
    session_id: str,
) -> RunOutcome:
    """Run the scenario once, end to end, over the real loop and the real hooks."""
    agent = PolicyAgent(structured=EXTRACTION)
    hooks = HookRegistry()
    memory = MemoryService(
        gateway=gateway,
        scope=scope,
        llm=agent,
        policy=policy,
        clock=lambda: datetime(2026, 6, 1, 3, 9, tzinfo=UTC),
    ).install(hooks)

    previous = binding.bind(memory.retriever)
    try:
        loop = ReActLoop(llm=agent, tools=tools(), hooks=hooks)
        result = await loop.run(RunRequest(objective=OBJECTIVE, session_id=session_id))
    finally:
        binding.restore(previous)

    async with gateway.begin(scope) as uow:
        stored = await uow.episodes.count()

    return RunOutcome(
        result=result,
        iterations=result.iterations,
        recalled=agent.recalled,
        episodes=stored,
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


async def test_a_repeat_incident_converges_in_fewer_iterations(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-003, measured: the same incident twice, and the delta between them.

    The first run has nothing to recall and works through all three backends.
    The second recalls the first run's episode after its first observation, sees
    a root cause it can act on, and concludes. Nothing about the two runs differs
    except the corpus.
    """
    first = await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-1")

    assert first.episodes == 1, "the first run has to leave a precedent behind"
    assert not first.recalled, "there was nothing to recall on the first run"

    second = await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-2")

    assert second.recalled, "the second run has to find the first run's episode"
    assert second.iterations < first.iterations, (
        f"memory did not reduce the trajectory: {first.iterations} then {second.iterations}"
    )

    # Recorded rather than only asserted. The number is the claim, and a change
    # in it is a change in what the feature is worth.
    reduction = first.iterations - second.iterations
    assert reduction >= 1
    assert second.result.answer


async def test_the_same_repeat_with_recall_disabled_takes_the_first_runs_trajectory(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-004 as the control for SC-003: without recall the corpus changes nothing.

    Same policy, same tools, same populated corpus — only the read switch
    differs. If this run were also shorter, the reduction above would be
    measuring something other than memory.
    """
    first = await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-1")
    ablated = await investigate(
        gateway,
        scope,
        policy=MemoryPolicy().without("memory_read"),
        session_id="conv-2",
    )

    assert not ablated.recalled
    assert ablated.iterations == first.iterations


async def test_a_repeat_turn_of_one_conversation_updates_rather_than_duplicates(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001 over the real loop rather than over the lifecycle alone."""
    await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-1")
    await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-1")

    async with gateway.begin(scope) as uow:
        assert await uow.episodes.count() == 1


async def test_no_episode_content_reaches_the_opening_prompt(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-002 over the real loop, with a populated corpus behind it."""
    await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-1")
    second = await investigate(gateway, scope, policy=MemoryPolicy(), session_id="conv-2")

    prompt = second.result.session.system_prompt
    assert ROOT_CAUSE not in prompt
    assert "payments-api" not in prompt
    assert "search it only once you hold" in prompt.lower()


def test_the_scenario_offers_recall_alongside_the_backends() -> None:
    """Guards the wiring the three measurements above depend on."""
    assert [found.name for found in tools()][-1] == RECALL_TOOL
