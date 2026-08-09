"""A whole investigation against a small local model, and what it costs.

Three things are proved here that none of the unit suites can, because each of
them is about the *whole stack* rather than about one mechanism.

**A well-behaved model pays nothing.** The same run is driven twice — once
through a bare provider client and once through the resilience layer — and the
two request sequences are compared for equality. Not "roughly the same number of
calls": the same calls, in the same order, with the same messages on them.

**A badly-behaved model still finishes.** A model that writes its tool calls as
prose, invents parameters and repeats itself runs a full investigation through
the canonical loop and comes back with an answer and a trace that says what it
took.

**An endpoint failure is not a model failure.** The two are distinguished, in
both directions, because sending an operator to their network when the answer is
"this model cannot tool call" wastes the part of the incident they cannot get
back.

There is no live model here and there is deliberately no path that would use one:
the misbehaviours are intermittent, so a test that asked a real small model to
misbehave would pass most of the time for the wrong reason. What a recorded
transcript cannot cover is the carry itself, and that is what ``make preflight``
is for.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from config.constants.llm import (
    MAX_TOOL_CALL_REPAIRS_PER_RUN,
    MODEL_CALL_BUDGET_SECONDS,
    PROVIDER_OLLAMA,
)
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.turn import GuardrailActionKind
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.llm.failures import FailureClass
from core.llm.health import EndpointStatus, check_endpoint
from core.llm.probe import ModelLimits
from core.llm.resilience import RepairBudget, ResilientClient
from core.llm.routing import TaskClass
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    Message,
    RepairKind,
    Role,
    StreamEvent,
    TokenEstimate,
    ToolCall,
)

MODEL = "qwen2.5:7b-instruct-q4_K_M"
ENDPOINT = "http://tower.lan:11434"


def _capability(name: str, payload: str) -> RegisteredTool:
    @tool(
        name=name,
        display_name=name,
        description=f"Return the recorded lines for {name}.",
        domain="observability",
        evidence_source="fixture",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    def body(namespace: str) -> str:
        """Return the recorded lines for ``namespace``."""
        return payload

    found = capability_marker(body)
    assert found is not None
    return found


LIST_PODS = _capability(
    "kubernetes_list_pods",
    "checkout-5f9c CrashLoopBackOff (OOMKilled ×7)\ncheckout-77ab Running\n",
)


@dataclass
class _Base:
    """The shared surface every model double in this file needs."""

    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return PROVIDER_OLLAMA

    @property
    def model_id(self) -> str:
        return MODEL

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=0, estimated=True)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        return await self.invoke(request)  # type: ignore[attr-defined]

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        if False:  # pragma: no cover — the loop never streams
            yield StreamEvent(kind=FinishReason.STOP)  # type: ignore[arg-type]


@dataclass
class WellBehavedModel(_Base):
    """Calls the tool once, then answers. Nothing here needs repairing."""

    turns: int = 0

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        self.turns += 1
        if self.turns == 1 and request.tools:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tool_calls=(
                    ToolCall(id="c1", name=LIST_PODS.name, arguments={"namespace": "checkout"}),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="checkout-5f9c is being OOM-killed; the memory limit is the cause.",
        )


@dataclass
class SmallLocalModel(_Base):
    """A seven-billion-parameter build, misbehaving the way they actually do.

    Turn one narrates its call instead of emitting one. Turn two invents a
    parameter. Turn three gets it right. Turn four repeats itself. Turn five
    answers. Every one of those is drawn from the recorded transcripts.
    """

    turns: int = 0

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        self.turns += 1
        corrected = any("was not made" in message.text for message in request.messages)

        if self.turns == 1:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                text=(
                    "I should look at the pods first.\n"
                    '{"name": "kubernetes_list_pods", "arguments": {"namespace": "checkout"}}'
                ),
            )
        if self.turns == 2 and not corrected:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tool_calls=(
                    ToolCall(
                        id="c2",
                        name=LIST_PODS.name,
                        arguments={"namespace": "payments", "label_selector": "app=checkout"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        if self.turns <= 4:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tool_calls=(
                    ToolCall(
                        id=f"c{self.turns}",
                        name=LIST_PODS.name,
                        arguments={"namespace": "payments"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="checkout-5f9c is being OOM-killed; the memory limit is the cause.",
        )


@dataclass
class SwappingEndpoint(_Base):
    """An endpoint on a machine that has started swapping. Never answers."""

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        await asyncio.sleep(60)
        raise AssertionError("the budget should have fired long before this")  # pragma: no cover


@dataclass
class UnreachableEndpoint(_Base):
    """The machine is off. The provider client degrades rather than raising."""

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            finish_reason=FinishReason.ERROR,
            partial=True,
            failure=FailureClass.TRANSIENT,
            failure_message="connection refused",
        )


@dataclass
class RefusingToCallTools(_Base):
    """The endpoint is fine. The model answers instead of calling anything."""

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="You should probably check the pods.",
        )


class TestAWellBehavedModelPaysNothing:
    async def test_the_layer_makes_exactly_the_calls_the_bare_client_would(self) -> None:
        bare, wrapped = WellBehavedModel(), WellBehavedModel()

        without = await ReActLoop(llm=bare, tools=[LIST_PODS]).run(
            RunRequest(objective="Why is checkout returning 503?", session_id="fixed")
        )
        with_layer = await ReActLoop(llm=ResilientClient(wrapped), tools=[LIST_PODS]).run(
            RunRequest(objective="Why is checkout returning 503?", session_id="fixed")
        )

        assert without.answer == with_layer.answer
        assert len(bare.requests) == len(wrapped.requests)
        for before, after in zip(bare.requests, wrapped.requests, strict=True):
            assert before.messages == after.messages
            assert [tool.name for tool in before.tools] == [tool.name for tool in after.tools]

    async def test_no_repair_is_recorded_on_a_clean_run(self) -> None:
        result = await ReActLoop(llm=ResilientClient(WellBehavedModel()), tools=[LIST_PODS]).run(
            RunRequest(objective="Why is checkout returning 503?")
        )

        assert not [
            action
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.MODEL_OUTPUT_REPAIRED
        ]

    async def test_the_clean_path_adds_no_round_trip(self) -> None:
        model = WellBehavedModel()

        await ReActLoop(llm=ResilientClient(model), tools=[LIST_PODS]).run(
            RunRequest(objective="Why is checkout returning 503?")
        )

        assert len(model.requests) == 2


class TestAnInvestigationAgainstASmallLocalModel:
    async def test_it_completes_and_says_what_it_found(self) -> None:
        model = SmallLocalModel()
        loop = ReActLoop(
            llm=ResilientClient(model, endpoint=ENDPOINT),
            tools=[LIST_PODS],
            limits=ModelLimits(usable_context_tokens=8_000, max_tool_schemas=8),
        )

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert result.status is RunStatus.COMPLETED
        assert "OOM-killed" in result.answer
        assert result.session.evidence

    async def test_the_trace_says_what_the_model_cost_in_attempts(self) -> None:
        model = SmallLocalModel()
        loop = ReActLoop(llm=ResilientClient(model, endpoint=ENDPOINT), tools=[LIST_PODS])

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        repaired = [
            action.reason
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.MODEL_OUTPUT_REPAIRED
        ]
        assert any(RepairKind.TOOL_CALL_EXTRACTED.value in reason for reason in repaired)
        assert any(RepairKind.UNKNOWN_ARGUMENT_REJECTED.value in reason for reason in repaired)

    async def test_the_run_records_which_model_produced_its_answer(self) -> None:
        loop = ReActLoop(llm=ResilientClient(SmallLocalModel()), tools=[LIST_PODS])

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert result.session.model_set == (f"{PROVIDER_OLLAMA}/{MODEL}",)
        assert all(entry.task == TaskClass.REASONING.value for entry in result.session.attributions)

    async def test_it_stays_inside_the_iteration_ceiling_it_was_given(self) -> None:
        loop = ReActLoop(llm=ResilientClient(SmallLocalModel()), tools=[LIST_PODS])

        result = await loop.run(
            RunRequest(objective="Why is checkout returning 503?", max_iterations=6)
        )

        assert result.session.iteration <= 6


class TestAModelThatCannotBeCorrected:
    async def test_the_run_degrades_with_the_behaviour_named_and_never_raises(self) -> None:
        @dataclass
        class AlwaysWrong(_Base):
            async def invoke(self, request: InvokeRequest) -> InvokeResult:
                self.requests.append(request)
                return InvokeResult(
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    tool_calls=(
                        ToolCall(id="c1", name=LIST_PODS.name, arguments={"selector": "x"}),
                    ),
                    finish_reason=FinishReason.TOOL_CALLS,
                )

        loop = ReActLoop(
            llm=ResilientClient(AlwaysWrong(), budget=RepairBudget(per_turn=2, per_run=2)),
            tools=[LIST_PODS],
        )

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert result.status is RunStatus.PARTIAL
        assert MODEL in (result.failure or "")
        assert RepairKind.UNKNOWN_ARGUMENT_REJECTED.value in (result.failure or "")

    async def test_the_bound_is_well_below_the_iteration_ceiling(self) -> None:
        assert MAX_TOOL_CALL_REPAIRS_PER_RUN < 20


class TestASlowEndpoint:
    async def test_a_call_past_its_budget_names_the_endpoint_and_the_elapsed_time(self) -> None:
        layer = ResilientClient(SwappingEndpoint(), endpoint=ENDPOINT, call_budget_seconds=0.05)

        result = await layer.invoke(
            InvokeRequest(messages=(Message(role=Role.USER, text="Why is checkout failing?"),))
        )

        assert result.partial
        assert ENDPOINT in result.failure_message
        assert "elapsed" in result.failure_message or "s)" in result.failure_message

    async def test_the_run_degrades_rather_than_hanging(self) -> None:
        loop = ReActLoop(
            llm=ResilientClient(SwappingEndpoint(), endpoint=ENDPOINT, call_budget_seconds=0.05),
            tools=[LIST_PODS],
        )

        result = await asyncio.wait_for(
            loop.run(RunRequest(objective="Why is checkout returning 503?")), timeout=5.0
        )

        assert result.status is RunStatus.PARTIAL

    def test_the_shipped_budget_is_below_the_run_ceiling(self) -> None:
        from config.constants.investigation import RUN_WALL_CLOCK_SECONDS

        assert MODEL_CALL_BUDGET_SECONDS < RUN_WALL_CLOCK_SECONDS


class TestAnEndpointFailureIsNotAModelFailure:
    async def test_an_unreachable_endpoint_reads_as_the_endpoint(self) -> None:
        health = await check_endpoint(UnreachableEndpoint(), endpoint=ENDPOINT)

        assert health.status is EndpointStatus.UNREACHABLE
        assert health.blames_the_endpoint
        assert ENDPOINT in health.render()

    async def test_a_model_that_will_not_call_tools_reads_as_the_model(self) -> None:
        layer = ResilientClient(RefusingToCallTools(), endpoint=ENDPOINT)

        health = await check_endpoint(layer, endpoint=ENDPOINT)

        # The health probe offers no tools, so answering in prose is a perfectly
        # good answer to it — the endpoint is up. What the model cannot do is the
        # probe's business, not this one's.
        assert health.status is EndpointStatus.REACHABLE
        assert not health.blames_the_endpoint

    async def test_a_misbehaving_model_is_reported_as_misbehaving_not_unreachable(self) -> None:
        @dataclass
        class Misbehaving(_Base):
            async def invoke(self, request: InvokeRequest) -> InvokeResult:
                self.requests.append(request)
                return InvokeResult(
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    finish_reason=FinishReason.ERROR,
                    partial=True,
                    failure=FailureClass.MODEL_BEHAVIOUR,
                    failure_message="kept inventing parameters",
                )

        health = await check_endpoint(Misbehaving(), endpoint=ENDPOINT)

        assert health.status is EndpointStatus.MODEL_MISBEHAVING
        assert not health.blames_the_endpoint

    async def test_an_endpoint_that_never_answers_is_unreachable_rather_than_slow(self) -> None:
        health = await check_endpoint(SwappingEndpoint(), endpoint=ENDPOINT, timeout_seconds=0.05)

        assert health.status is EndpointStatus.UNREACHABLE
        assert "0" in health.detail

    @pytest.mark.parametrize(
        ("failure", "expected"),
        [
            (FailureClass.AUTH, EndpointStatus.UNAUTHENTICATED),
            (FailureClass.MODEL_UNAVAILABLE, EndpointStatus.MODEL_MISSING),
            (FailureClass.RATE_LIMITED, EndpointStatus.UNREACHABLE),
            (FailureClass.UNKNOWN, EndpointStatus.UNREACHABLE),
        ],
    )
    async def test_each_failure_class_reads_as_the_verdict_it_should(
        self, failure: FailureClass, expected: EndpointStatus
    ) -> None:
        @dataclass
        class Failing(_Base):
            async def invoke(self, request: InvokeRequest) -> InvokeResult:
                self.requests.append(request)
                return InvokeResult(
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    finish_reason=FinishReason.ERROR,
                    partial=True,
                    failure=failure,
                    failure_message="recorded",
                )

        assert (await check_endpoint(Failing(), endpoint=ENDPOINT)).status is expected
