"""The layer between the adapter and the runtime, driven by hand.

The fixture suite in ``tests/contract/llm/test_misbehaving_models.py`` drives the
same layer from recorded transcripts. This file is the unit half: one
misbehaviour per test, with the boundary conditions the fixtures do not carry.

The load-bearing test in here is the last class. Every other assertion is about
handling a model's mistake gracefully; that one is about never covering one up
by inventing a value the model did not supply, and it is structural rather than
behavioural on purpose — a behavioural test proves the paths it exercised.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from config.constants.llm import (
    MAX_IDENTICAL_CALLS_IN_WINDOW,
    MAX_TOOL_CALL_REPAIRS_PER_RUN,
    MAX_TOOL_CALL_REPAIRS_PER_TURN,
    PROVIDER_OLLAMA,
    SUPPORTED_PROVIDERS,
)
from core.llm.failures import FailureClass
from core.llm.resilience import (
    RepairBudget,
    RepetitionDetector,
    ResilientClient,
    check_arguments,
    extract_tool_call,
)
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    Message,
    RepairKind,
    Role,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
    ToolSchema,
)

LIST_PODS = ToolSchema(
    name="kubernetes_list_pods",
    description="List the pods in one namespace.",
    parameters={
        "type": "object",
        "properties": {
            "namespace": {"type": "string"},
            "phase": {"type": "string"},
        },
        "required": ["namespace"],
    },
)


@dataclass
class ScriptedClient:
    """Replays a queue of results and records every request it was sent."""

    results: list[InvokeResult] = field(default_factory=list)
    events: list[StreamEvent] = field(default_factory=list)
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return PROVIDER_OLLAMA

    @property
    def model_id(self) -> str:
        return "qwen2.5:7b"

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=0, estimated=True)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        if not self.results:
            raise AssertionError("the layer sent more requests than the script answers")
        return self.results.pop(0)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        return await self.invoke(request)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event


def _result(
    *,
    text: str = "",
    tool_calls: tuple[ToolCall, ...] = (),
) -> InvokeResult:
    return InvokeResult(
        provider_id=PROVIDER_OLLAMA,
        model_id="qwen2.5:7b",
        text=text,
        tool_calls=tool_calls,
        finish_reason=FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP,
    )


def _request(*, tools: tuple[ToolSchema, ...] = (LIST_PODS,), session: str = "s1") -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="Why is checkout failing?"),),
        tools=tools,
        metadata={"session_id": session},
    )


class TestATollCallEmittedAsText:
    def test_a_bare_json_call_is_extracted(self) -> None:
        extraction = extract_tool_call(
            'I will check. {"name": "kubernetes_list_pods", "arguments": {"namespace": "checkout"}}',
            (LIST_PODS,),
        )

        assert extraction.call == ToolCall(
            id=extraction.call.id if extraction.call else "",
            name="kubernetes_list_pods",
            arguments={"namespace": "checkout"},
        )

    def test_a_fenced_call_with_the_other_spelling_is_extracted(self) -> None:
        extraction = extract_tool_call(
            '```json\n{"tool": "kubernetes_list_pods", "parameters": {"namespace": "pay"}}\n```',
            (LIST_PODS,),
        )

        assert extraction.call is not None
        assert extraction.call.arguments == {"namespace": "pay"}

    def test_a_call_naming_a_capability_that_was_not_offered_is_not_a_call(self) -> None:
        extraction = extract_tool_call(
            '{"name": "delete_everything", "arguments": {}}', (LIST_PODS,)
        )

        assert extraction.call is None

    def test_prose_that_happens_to_contain_a_brace_is_not_a_call(self) -> None:
        extraction = extract_tool_call(
            "The selector {app=checkout} matches two pods, which is the problem.", (LIST_PODS,)
        )

        assert extraction.call is None
        assert extraction.named == ""

    def test_text_that_names_a_capability_but_cannot_be_read_says_which(self) -> None:
        extraction = extract_tool_call(
            'Calling kubernetes_list_pods with {"namespace": ', (LIST_PODS,)
        )

        assert extraction.call is None
        assert extraction.named == "kubernetes_list_pods"

    async def test_the_extraction_is_recorded_as_a_repair_not_a_clean_call(self) -> None:
        client = ScriptedClient(
            results=[
                _result(
                    text='{"name": "kubernetes_list_pods", "arguments": {"namespace": "checkout"}}'
                )
            ]
        )
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert [call.name for call in result.tool_calls] == ["kubernetes_list_pods"]
        assert [repair.kind for repair in result.repairs] == [RepairKind.TOOL_CALL_EXTRACTED]


class TestAnArgumentTheSchemaDoesNotDeclare:
    def test_the_parameter_is_named(self) -> None:
        verdict = check_arguments(
            ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a", "selector": "b"}),
            LIST_PODS,
        )

        assert verdict.unknown == ("selector",)
        assert not verdict.acceptable

    async def test_the_capability_is_not_called_and_the_model_is_told_which(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a", "selector": "b"})
        good = ToolCall(id="2", name=LIST_PODS.name, arguments={"namespace": "a"})
        client = ScriptedClient(results=[_result(tool_calls=(bad,)), _result(tool_calls=(good,))])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.tool_calls == (good,)
        assert any(repair.parameter == "selector" for repair in result.repairs)
        correction = client.requests[-1].messages[-1].text
        assert "selector" in correction
        assert "namespace" in correction

    async def test_the_rejected_call_never_reaches_the_caller(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a", "selector": "b"})
        client = ScriptedClient(
            results=[_result(tool_calls=(bad,))] * (MAX_TOOL_CALL_REPAIRS_PER_TURN + 1)
        )
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.tool_calls == ()


class TestAMissingRequiredArgument:
    def test_the_missing_parameter_is_named_and_nothing_is_supplied_for_it(self) -> None:
        verdict = check_arguments(
            ToolCall(id="1", name=LIST_PODS.name, arguments={"phase": "Running"}), LIST_PODS
        )

        assert verdict.missing == ("namespace",)
        assert verdict.call.arguments == {"phase": "Running"}

    async def test_the_correction_is_specific_rather_than_a_validation_error(self) -> None:
        client = ScriptedClient(
            results=[
                _result(tool_calls=(ToolCall(id="1", name=LIST_PODS.name, arguments={}),)),
                _result(
                    tool_calls=(
                        ToolCall(id="2", name=LIST_PODS.name, arguments={"namespace": "a"}),
                    )
                ),
            ]
        )
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        correction = client.requests[-1].messages[-1].text
        assert "namespace" in correction
        assert "kubernetes_list_pods" in correction
        assert [repair.kind for repair in result.repairs] == [RepairKind.MISSING_ARGUMENT_REPORTED]


class TestRepairsAreBounded:
    def test_a_budget_counts_a_turn_and_a_run_separately(self) -> None:
        budget = RepairBudget(per_turn=2, per_run=3)

        assert budget.spend()
        assert budget.spend()
        assert not budget.spend()

        budget.next_turn()
        assert budget.spend()
        assert not budget.spend()

    async def test_a_turn_stops_correcting_at_its_bound(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"selector": "b"})
        client = ScriptedClient(results=[_result(tool_calls=(bad,))] * 10)
        layer = ResilientClient(client)

        await layer.invoke(_request())

        assert len(client.requests) == MAX_TOOL_CALL_REPAIRS_PER_TURN + 1

    async def test_a_run_stops_correcting_at_its_own_bound(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"selector": "b"})
        client = ScriptedClient(results=[_result(tool_calls=(bad,))] * 100)
        layer = ResilientClient(client)

        for _ in range(MAX_TOOL_CALL_REPAIRS_PER_RUN):
            await layer.invoke(_request())
        before = len(client.requests)
        await layer.invoke(_request())

        assert len(client.requests) - before == 1


class TestExhaustingTheBoundDegrades:
    async def test_the_failure_names_the_model_behaviour_and_never_raises(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"selector": "b"})
        client = ScriptedClient(results=[_result(tool_calls=(bad,))] * 10)
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.partial
        assert result.failure is FailureClass.MODEL_BEHAVIOUR
        assert "qwen2.5:7b" in result.failure_message
        assert result.repairs

    async def test_a_degraded_result_keeps_every_repair_that_led_to_it(self) -> None:
        bad = ToolCall(id="1", name=LIST_PODS.name, arguments={"selector": "b"})
        client = ScriptedClient(results=[_result(tool_calls=(bad,))] * 10)
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert len(result.repairs) >= MAX_TOOL_CALL_REPAIRS_PER_TURN


class TestAModelStuckOnOneCall:
    def test_the_detector_fires_inside_its_window(self) -> None:
        detector = RepetitionDetector()
        call = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a"})

        verdicts = [detector.observe("s1", (call,)) for _ in range(MAX_IDENTICAL_CALLS_IN_WINDOW)]

        assert not verdicts[0].repeating
        assert verdicts[-1].repeating
        assert verdicts[-1].capability == LIST_PODS.name

    def test_a_different_argument_resets_nothing_but_is_not_a_repeat(self) -> None:
        detector = RepetitionDetector()
        for namespace in ("a", "b", "c", "d"):
            verdict = detector.observe(
                "s1", (ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": namespace}),)
            )

        assert not verdict.repeating

    def test_two_sessions_do_not_see_each_other(self) -> None:
        detector = RepetitionDetector()
        call = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a"})

        for _ in range(MAX_IDENTICAL_CALLS_IN_WINDOW):
            detector.observe("s1", (call,))
        verdict = detector.observe("s2", (call,))

        assert not verdict.repeating

    async def test_the_model_is_told_and_the_loop_is_broken_before_the_ceiling(self) -> None:
        call = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a"})
        moved_on = ToolCall(id="2", name=LIST_PODS.name, arguments={"namespace": "b"})
        client = ScriptedClient(
            results=[_result(tool_calls=(call,))] * MAX_IDENTICAL_CALLS_IN_WINDOW
            + [_result(tool_calls=(moved_on,))]
        )
        layer = ResilientClient(client)

        for _ in range(MAX_IDENTICAL_CALLS_IN_WINDOW - 1):
            await layer.invoke(_request())
        result = await layer.invoke(_request())

        assert any(repair.kind is RepairKind.REPETITION_BROKEN for repair in result.repairs)
        assert result.tool_calls == (moved_on,)
        told = client.requests[-1].messages[-1].text
        assert LIST_PODS.name in told


class TestDuplicateCallsInOneTurn:
    async def test_the_second_copy_is_dropped_before_anything_runs(self) -> None:
        call = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a"})
        twin = ToolCall(id="2", name=LIST_PODS.name, arguments={"namespace": "a"})
        client = ScriptedClient(results=[_result(tool_calls=(call, twin))])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.tool_calls == (call,)
        assert any(repair.kind is RepairKind.DUPLICATE_CALL_DISCARDED for repair in result.repairs)

    async def test_two_genuinely_different_calls_are_both_kept(self) -> None:
        first = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "a"})
        second = ToolCall(id="2", name=LIST_PODS.name, arguments={"namespace": "b"})
        client = ScriptedClient(results=[_result(tool_calls=(first, second))])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.tool_calls == (first, second)
        assert result.repairs == ()


class TestAWellBehavedModelPaysNothing:
    async def test_one_call_in_one_call_out_with_no_repairs(self) -> None:
        good = ToolCall(id="1", name=LIST_PODS.name, arguments={"namespace": "checkout"})
        client = ScriptedClient(results=[_result(tool_calls=(good,))])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert len(client.requests) == 1
        assert result.tool_calls == (good,)
        assert result.repairs == ()

    async def test_a_text_answer_with_no_call_is_left_alone(self) -> None:
        client = ScriptedClient(results=[_result(text="The cause is connection pool exhaustion.")])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert len(client.requests) == 1
        assert result.text == "The cause is connection pool exhaustion."
        assert result.repairs == ()

    async def test_a_provider_failure_passes_straight_through(self) -> None:
        failed = InvokeResult(
            provider_id=PROVIDER_OLLAMA,
            model_id="qwen2.5:7b",
            finish_reason=FinishReason.ERROR,
            partial=True,
            failure=FailureClass.AUTH,
            failure_message="rejected the key",
        )
        client = ScriptedClient(results=[failed])
        layer = ResilientClient(client)

        result = await layer.invoke(_request())

        assert result.failure is FailureClass.AUTH
        assert len(client.requests) == 1


class TestStreamedFragments:
    async def test_the_pieces_of_one_call_are_put_back_together(self) -> None:
        client = ScriptedClient(
            events=[
                StreamEvent(kind=StreamEventKind.TEXT_DELTA, text="Pulling the logs. "),
                StreamEvent(
                    kind=StreamEventKind.TOOL_CALL,
                    tool_call=ToolCall(id="c1", name=LIST_PODS.name),
                    tool_call_fragment='{"namespace": "che',
                ),
                StreamEvent(
                    kind=StreamEventKind.TOOL_CALL,
                    tool_call=ToolCall(id="c1", name=""),
                    tool_call_fragment='ckout"}',
                ),
                StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.TOOL_CALLS),
            ]
        )
        layer = ResilientClient(client)

        events = [event async for event in layer.stream(_request())]

        calls = [event.tool_call for event in events if event.kind is StreamEventKind.TOOL_CALL]
        assert len(calls) == 1
        assert calls[0] is not None
        assert calls[0].arguments == {"namespace": "checkout"}

    async def test_an_unfragmented_stream_is_passed_through_unchanged(self) -> None:
        events_in = [
            StreamEvent(kind=StreamEventKind.TEXT_DELTA, text="one "),
            StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP),
        ]
        client = ScriptedClient(events=list(events_in))
        layer = ResilientClient(client)

        assert [event async for event in layer.stream(_request())] == events_in


class TestTheLayerIsProviderNeutral:
    def test_no_module_in_the_layer_names_a_provider(self) -> None:
        package = Path(__file__).resolve().parents[4] / "core" / "llm" / "resilience"
        sources = {path: path.read_text(encoding="utf-8") for path in package.glob("*.py")}

        assert sources, "the resilience package has no modules to check"
        for path, source in sources.items():
            for provider_id in SUPPORTED_PROVIDERS:
                assert provider_id not in source, f"{path.name} mentions {provider_id}"


class TestNoRepairPathCanInventAValue:
    """SC-010, asserted structurally rather than by exercising paths.

    A behavioural test proves the arguments it happened to pass. What has to
    hold is that there is no path at all — so this reads the package's own
    syntax tree and asserts that a ``ToolCall`` is only ever constructed inside
    the one function that verifies every value it carries came from the model's
    own output.
    """

    @staticmethod
    def _tree() -> dict[str, ast.Module]:
        package = Path(__file__).resolve().parents[4] / "core" / "llm" / "resilience"
        return {
            path.name: ast.parse(path.read_text(encoding="utf-8")) for path in package.glob("*.py")
        }

    def test_tool_calls_are_only_built_where_their_values_are_verified(self) -> None:
        from core.llm.resilience.extraction import SOLE_CONSTRUCTION_SITE

        built_in: list[str] = []
        for name, module in self._tree().items():
            for node in ast.walk(module):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for inner in ast.walk(node):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "ToolCall"
                    ):
                        built_in.append(f"{name}:{node.name}")

        assert set(built_in) == {SOLE_CONSTRUCTION_SITE}

    def test_the_verifier_refuses_a_value_that_is_not_in_the_model_output(self) -> None:
        from core.llm.resilience.extraction import InventedValueError, verified_arguments

        with pytest.raises(InventedValueError):
            verified_arguments({"namespace": "checkout"}, source='{"namespace": "payments"}')

    def test_the_verifier_accepts_what_the_model_actually_wrote(self) -> None:
        from core.llm.resilience.extraction import verified_arguments

        source = '{"namespace": "checkout", "limit": 200, "live": true}'

        assert verified_arguments(
            {"namespace": "checkout", "limit": 200, "live": True}, source=source
        ) == {"namespace": "checkout", "limit": 200, "live": True}

    def test_a_missing_required_argument_is_never_filled_in(self) -> None:
        verdict = check_arguments(
            ToolCall(id="1", name=LIST_PODS.name, arguments={}),
            LIST_PODS,
        )

        assert verdict.call.arguments == {}
        assert verdict.missing == ("namespace",)
