"""What each learning mechanism is worth, measured by removing it and running again.

This is the feature's proof, and it is the first place in the repository where
Constitution Article VII stops being a rule and becomes a number. The claim under
test is not "memory is a good idea"; it is "episodic recall raises the level-3
solve rate by N points and shortens the trajectory by M calls", and the only way
to say that honestly is to run the same corpus with recall switched off.

**Everything except the switch is real.** The hooks are the real registry, the
memory service is the real one over a real populated corpus, the knowledge
guidance is the real hook, the loop is the canonical ReAct loop, the capabilities
are real registrations, and the scoring is the same five-axis scorer the gate
uses. The switches come from ``MechanismSwitches``, which reaches each owning
feature's own control.

**The agent double is a policy, not a script.** It reads the system prompt the
hooks actually built and the recall results the tools actually returned, and
decides from what is there. That is what lets the arms differ *because* the
mechanism was removed rather than because the fixture said so. It is crude next to
a real model and it is stated here in the open: what this measures is the
mechanism — a warning reaching the agent early enough to change the trajectory —
not how reliably a particular model exploits one.

**A mechanism that changes nothing must report nothing.** Five of the eight are
not exercised by this corpus at all, and the report has to say "no measurable
effect" for them rather than inventing a percentage point. A harness that could
not produce an honest zero could not produce an honest number either.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from capabilities.tools.system.memory_search import binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL_TOOL
from capabilities.tools.system.memory_search.tool import recall_similar_incidents
from config.constants.evaluation import ABLATION_MECHANISMS, AXIS_ACCURACY, AXIS_TRAJECTORY
from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from config.prompts.knowledge import TOPOLOGY_GUIDANCE
from core.agent.hooks.registry import HookRegistry
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest
from core.agent.seed_calls import EMPTY_SEED_CATALOGUE
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
from platform.knowledge.guidance import KnowledgeGuidance
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import embed_one
from platform.memory.models import Component, MemoryEpisode
from platform.memory.service import MemoryService
from platform.memory.strategy.models import StrategySection
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import VectorRecord
from tests.harness.ablation.report import report_for
from tests.harness.ablation.runner import run_ablation
from tests.harness.ablation.switches import MechanismSwitches
from tests.harness.loader import AnswerKey, GoldenTrajectory, Scenario
from tests.harness.scoring.composite import Observation
from tests.harness.scoring.matching import steps_of

pytestmark = pytest.mark.synthetic

ORG = "acme"
TEAM = "team-payments"
NOW = datetime(2026, 8, 7, 3, 9, tzinfo=UTC)

ROOT_CAUSE = "the 02:50 deploy lowered the container memory limit from 1Gi to 512Mi"

#: The approach three previous investigations took and established nothing with.
#: It returns something — that is what makes it a dead end rather than a broken
#: tool — and what it returns bears on nothing.
DEAD_END = "broker_metrics"

#: The backends in the order a run with no guidance works through them. The dead
#: end is first, which is the case an anti-patterns section exists for.
BACKENDS: tuple[tuple[str, str], ...] = (
    (DEAD_END, "consumer lag on payments-events is 0 and has been flat for six hours"),
    ("payments_dependency_health", "the payments-ledger dependency is healthy and responding"),
    ("kubernetes_pod_events", "3 OOMKilled events on payments-api between 03:04 and 03:09"),
    ("kubernetes_describe_workload", "container payments-api last state OOMKilled, limit 512Mi"),
    ("deploy_history", f"release 4.19.2 deployed at 02:50: {ROOT_CAUSE}"),
)

#: What the dependency-scoping paragraph lets an agent skip. Only reachable when
#: topology guidance is in the prompt, which is what makes topology's contribution
#: attributable to topology.
TOPOLOGY_SKIP = "payments_dependency_health"

CONCLUSION = (
    "payments-api entered CrashLoopBackOff at 03:04 UTC. Every restart is an OOMKill on the "
    f"api container, and {ROOT_CAUSE}. The coincident traffic peak had already subsided, and "
    "the payments-ledger dependency stayed healthy throughout. Raising the limit back to 1Gi "
    "is expected to resolve it."
)

PLAYBOOK: Mapping[str, Any] = {
    StrategySection.ROOT_CAUSES.value: ["A deploy lowering the container memory limit"],
    StrategySection.INVESTIGATION_STEPS.value: ["Read the workload's last termination state"],
    StrategySection.CAPABILITIES.value: ["kubernetes_describe_workload on the failing workload"],
    StrategySection.ANTI_PATTERNS.value: [
        f"{DEAD_END} — three previous runs started there, found flat lag, and established nothing",
    ],
}

EXTRACTION: Mapping[str, Any] = {
    "issue_type": "oom_kill",
    "issue_description": "payments-api restarting with exit code 137",
    "severity": "high",
    "components": [{"type": "service", "name": "payments-api"}],
    "key_findings": [],
    "resolved": True,
    "root_cause": ROOT_CAUSE,
    "summary": "release 4.19.2 lowered the container memory limit from 1Gi to 512Mi.",
}


# -- the corpus ----------------------------------------------------------------


ANSWER = AnswerKey(
    root_cause_category="resource_exhaustion",
    required_keywords=("memory", "limit"),
    model_response=f"ROOT_CAUSE: {ROOT_CAUSE}\n",
    ruling_out_keywords=("traffic", "dependency"),
    required_evidence_sources=("kubernetes",),
    golden_trajectory=GoldenTrajectory(
        ordered_actions=("kubernetes_describe_workload", "deploy_history"),
        matching="set",
        max_edit_distance=2,
        max_extra_actions=2,
        max_redundancy=0,
    ),
    max_investigation_loops=8,
)


def scenario(scenario_id: str, *, difficulty: int) -> Scenario:
    """Return one scenario of the ablation corpus at ``difficulty``."""
    return Scenario(
        directory=Path("kubernetes") / scenario_id,
        suite="kubernetes",
        scenario_id=scenario_id,
        failure_mode="misconfigured_limit",
        severity="critical",
        difficulty=difficulty,
        adversarial_signals=("coincident_deployment", "coincident_traffic_spike"),
        available_evidence=("kubernetes",),
        integrations=("kubernetes",),
        alert={"text": "payments-api pods are in CrashLoopBackOff"},
        answer=ANSWER,
        evidence=(),
    )


#: Four scenarios across the ladder. The easy ones are solvable by working
#: through the backends in order within the loop ceiling; the hard ones are not,
#: which is what makes a mechanism's contribution show up at one level and not
#: another.
CORPUS = (
    scenario("001-easy", difficulty=1),
    scenario("002-easy", difficulty=1),
    scenario("003-hard", difficulty=3),
    scenario("004-hard", difficulty=3),
)

#: How many iterations a level-3 scenario is given. Tight enough that the dead
#: end costs the run its answer, which is the mechanism being priced.
HARD_BUDGET = 3
EASY_BUDGET = 8


def budget_for(subject: Scenario) -> int:
    """Return how many iterations this scenario's investigation is given."""
    return EASY_BUDGET if subject.difficulty < 3 else HARD_BUDGET


# -- the capabilities ----------------------------------------------------------


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


# -- the agent -----------------------------------------------------------------


@dataclass(slots=True)
class PolicyAgent:
    """Work through the backends, skipping what the guidance it was given rules out.

    Reads the system prompt the hooks actually built and the recall results the
    tools actually returned. Nothing about the arms is written into this class:
    it behaves differently across arms because it is *told* different things.
    """

    budget: int
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
        """Return the next move, given the prompt and what has come back so far."""
        self.turns += 1
        offered = {schema.name for schema in request.tools}
        if not offered:
            return self._answer()

        prompt = request.system or ""
        results = [result for message in request.messages for result in message.tool_results]
        gathered = [
            result for result in results if result.name != RECALL_TOOL and not result.is_error
        ]
        recalls = [result for result in results if result.name == RECALL_TOOL]

        # Memory guidance is what tells this agent recall exists. Without the
        # paragraph the tool is in the catalogue and nothing points at it, which
        # is the real effect of switching episodic read off.
        wants_memory = "previous investigation" in prompt.lower() or "memory" in prompt.lower()
        if wants_memory and not self.searched_memory and RECALL_TOOL in offered:
            self.searched_memory = True
            return self._call(RECALL_TOOL, {"query": "payments-api", "issue_type": "oom_kill"})

        self._read_playbook(recalls)

        # Topology guidance is what tells this agent to scope by dependency
        # rather than to probe each one. It is the only thing that makes the
        # dependency check skippable, so topology's contribution is topology's.
        if TOPOLOGY_GUIDANCE[:40] in prompt:
            self.avoided.add(TOPOLOGY_SKIP)

        if any(ROOT_CAUSE in result.content for result in gathered):
            return self._answer()
        if len(gathered) >= self.budget:
            return self._give_up()

        called = {result.name for result in gathered}
        remaining = [
            name
            for name, _ in BACKENDS
            if name not in called and name not in self.avoided and name in offered
        ]
        if remaining:
            return self._call(remaining[0], {"query": "payments-api"})
        return self._give_up()

    def _read_playbook(self, recalls: Sequence[Any]) -> None:
        """Note which capabilities a returned playbook warned against."""
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

    def _give_up(self) -> InvokeResult:
        """Return the honest non-answer of a run that spent its budget elsewhere."""
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=(
                "payments-api is restarting and I have not established why within the "
                "iterations available. The consumer lag is flat."
            ),
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


# -- the corpus of previous investigations -------------------------------------


def prior_episode(index: int, *, resolved: bool) -> MemoryEpisode:
    """Return one previous investigation of this failure on this component."""
    return MemoryEpisode(
        correlation_id=f"prior-{index}",
        org_id=ORG,
        team_node_id=TEAM,
        issue_type="oom_kill",
        issue_description="payments-api restarting with exit code 137",
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


@pytest.fixture
async def populated() -> AsyncIterator[PersistenceGateway]:
    """Yield a gateway carrying five previous investigations of this failure."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")

    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    embedder = LocalEmbedder()
    corpus = (
        prior_episode(1, resolved=True),
        prior_episode(2, resolved=True),
        prior_episode(3, resolved=True),
        prior_episode(4, resolved=False),
        prior_episode(5, resolved=False),
    )
    async with store.begin(scope) as uow:
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
    yield store
    await store.close()


# -- the arm runner ------------------------------------------------------------


def arm_runner(gateway: PersistenceGateway) -> Any:
    """Return an arm runner that stands up the real stack under one arm's switches."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)

    async def run(subject: Scenario, switches: MechanismSwitches, attempt: int) -> Observation:
        agent = PolicyAgent(budget=budget_for(subject))
        hooks = HookRegistry()

        MemoryService(
            gateway=gateway,
            scope=scope,
            llm=agent,
            policy=switches.memory,
            strategy_policy=switches.strategies,
            clock=lambda: NOW,
        ).install(hooks)

        # The real knowledge hook, gated on the real policy. Registered only when
        # a switch is on, so "off" is the code path a deployment without the
        # store takes rather than a hook that returns early.
        if switches.knowledge.enabled:
            KnowledgeGuidance(policy=switches.knowledge).register(hooks)

        previous = binding.bind(
            MemoryService(
                gateway=gateway,
                scope=scope,
                llm=agent,
                policy=switches.memory,
                strategy_policy=switches.strategies,
                clock=lambda: NOW,
            ).recall
        )
        try:
            loop = ReActLoop(
                llm=agent,
                tools=tools(),
                hooks=hooks,
                subagents=switches.subagents(()),
                seed_catalogue=switches.seed_catalogue(EMPTY_SEED_CATALOGUE),
            )
            result = await loop.run(
                RunRequest(
                    objective="payments-api pods are in CrashLoopBackOff",
                    session_id=f"{subject.key}-{attempt}-{'-'.join(switches.disabled_mechanisms())}",
                )
            )
        finally:
            binding.restore(previous)

        called = tuple(name for name in agent.calls if name != RECALL_TOOL)
        solved = ROOT_CAUSE in result.answer
        return Observation(
            root_cause_category="resource_exhaustion" if solved else "unknown",
            answer_text=result.answer,
            evidence_sources=("kubernetes",) if called else (),
            trajectory=steps_of(called),
            iterations=result.iterations,
            tokens=520 * max(result.iterations, 1),
            duration_seconds=0.5,
            provider_id=agent.provider_id,
            model_id=agent.model_id,
        )

    return run


# -- the measurement (T045–T048, SC-003, SC-004) -------------------------------


async def test_the_full_ablation_prices_every_mechanism_over_the_whole_ladder(
    populated: PersistenceGateway,
) -> None:
    """T045 and T046: nine arms across four scenarios at two difficulty levels.

    The whole point of the harness in one call. Every mechanism gets an arm,
    every arm runs the whole corpus, and the report has to come back with a
    contribution or an honest zero for each.
    """
    result = await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1)

    assert result.failed_arms == (), "an arm that could not run prices nothing"
    assert len(result.arms) == len(ABLATION_MECHANISMS) + 1

    report = report_for(result)
    assert set(report.mechanisms) == set(ABLATION_MECHANISMS)
    assert report.unmeasured == ()


async def test_episodic_recall_and_synthesis_are_worth_measurable_accuracy(
    populated: PersistenceGateway,
) -> None:
    """SC-003 and T048: the first quantified learning claim, as an assertion.

    The mechanism: with recall on, the agent is told previous runs exist, asks,
    and is handed a playbook whose anti-patterns name the approach that never
    works. It skips the dead end and reaches the cause inside a level-3 budget.
    With recall off it pays for the dead end and runs out of iterations.
    """
    report = report_for(await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1))

    memory = next(
        found
        for found in report.for_mechanism("memory_read")
        if found.axis == AXIS_ACCURACY and found.difficulty is None
    )
    strategy = next(
        found
        for found in report.for_mechanism("memory_strategy")
        if found.axis == AXIS_ACCURACY and found.difficulty is None
    )

    assert memory.delta > 0.0, (
        f"recall was worth nothing on this corpus: {memory.baseline_rate:.0%} with it, "
        f"{memory.ablated_rate:.0%} without"
    )
    assert strategy.delta > 0.0, "the playbook is what carries the anti-pattern; it must matter"
    assert memory.measurable and strategy.measurable


async def test_the_contribution_is_reported_per_difficulty_level(
    populated: PersistenceGateway,
) -> None:
    """SC-003's second half: a mechanism that pays on hard scenarios and not easy ones.

    This is the finding the stratification exists for. Both rungs solve the
    incident when there is budget to work through every backend; only the tight
    one is changed by being told which backend not to bother with.
    """
    report = report_for(await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1))

    by_level = {
        found.difficulty: found
        for found in report.for_mechanism("memory_read")
        if found.axis == AXIS_ACCURACY and found.difficulty is not None
    }

    assert by_level[1].delta == pytest.approx(0.0), "the easy rung has budget to spare"
    assert by_level[3].delta > 0.0, "the tight rung is where knowing what to skip pays"


async def test_topology_shortens_the_route_everywhere_and_buys_the_answer_where_budget_is_tight(
    populated: PersistenceGateway,
) -> None:
    """SC-003's third mechanism, and the clearest case for per-axis, per-level reporting.

    Topology guidance lets the agent scope by dependency rather than probe one.
    On a scenario with iterations to spare that is a pure route change — the same
    answer, one call earlier. On the tight rung the saved call is the one that
    would have reached the cause, so the *same* mechanism shows up on a second
    axis at a second level.

    A report that gave topology one number could not say that, and the number it
    gave would be an average over two different findings.
    """
    result = await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1)
    report = report_for(result)

    without = result.arm("no-topology")
    assert without is not None

    with_it = result.baseline.suite.scenario("kubernetes/001-easy")
    ablated = without.suite.scenario("kubernetes/001-easy")
    assert with_it is not None and ablated is not None

    calls_with = with_it.measurement("trajectory.iterations")
    calls_without = ablated.measurement("trajectory.iterations")
    assert calls_with is not None and calls_without is not None
    assert calls_with.mean < calls_without.mean, (
        "topology guidance did not shorten the route, so it is worth nothing here"
    )

    by_level = {
        found.difficulty: found
        for found in report.for_mechanism("topology")
        if found.axis == AXIS_ACCURACY and found.difficulty is not None
    }
    assert by_level[1].delta == pytest.approx(0.0), (
        "on the easy rung there is budget to spare, so a shorter route changes no answer"
    )
    assert by_level[3].delta > 0.0, (
        "on the tight rung the call topology saves is the one that reaches the cause"
    )

    assert any(found.axis == AXIS_TRAJECTORY for found in report.for_mechanism("topology")), (
        "topology has to be priced on the trajectory axis as well as the accuracy one"
    )


async def test_a_mechanism_this_corpus_does_not_exercise_reports_an_honest_zero(
    populated: PersistenceGateway,
) -> None:
    """A harness that cannot produce an honest zero cannot produce an honest number.

    Sub-agents, seed calls, masking, and capability planning do nothing in this
    scenario, and the report must say so rather than attribute a percentage point
    to whichever way the noise fell.
    """
    report = report_for(await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1))

    for name in ("subagents", "seed_calls", "capability_planning", "masking"):
        corpus_wide = [found for found in report.for_mechanism(name) if found.difficulty is None]
        assert corpus_wide, f"{name} was not priced at all"
        assert all(not found.measurable for found in corpus_wide), (
            f"{name} moved a number in a scenario that does not exercise it"
        )
    assert not report.harmful


async def test_every_arm_differs_from_the_baseline_in_exactly_one_respect(
    populated: PersistenceGateway,
) -> None:
    """SC-004, over the real stack: verified by comparing the arms' traces.

    The assertion the whole table rests on. If an arm moved two keys, the
    contribution attributed to its mechanism would be the sum of two effects and
    nothing in the report would say so.
    """
    result = await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1)
    baseline = result.baseline.configuration

    for arm in result.arms:
        if arm.config.is_baseline:
            continue
        moved = {key for key in baseline if baseline[key] != arm.configuration[key]}
        assert len(moved) == 1, (
            f"{arm.config.name} moved {sorted(moved)}; an arm has to differ from the "
            f"baseline in exactly one respect or its number is the sum of two effects"
        )
        assert set(arm.configuration) == set(baseline)


async def test_the_report_renders_the_claim_a_release_note_would_carry(
    populated: PersistenceGateway,
) -> None:
    """T048: the number goes in the release notes, so it has to be printable."""
    report = report_for(await run_ablation(CORPUS, arm=arm_runner(populated), attempts=1))
    text = report.render()

    assert "memory_read" in text
    assert "contribution per mechanism" in text
    assert "by difficulty" in text
    assert report.corpus_version
