"""Running the canonical loop against a model with no room in it.

Three mechanisms meet here and they are only worth testing together: the
transcript is compacted before the model's *measured* context is reached rather
than at a message count; the number of schemas a turn carries respects what the
model demonstrated it can hold; and every one of those is a line in the trace,
because a run that quietly dropped half its conversation and produced a thin
answer is one nobody can debug afterwards.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
)
from config.constants.llm import PROVIDER_OLLAMA
from core.agent.compaction import COMPACTION_STRATEGY, compact
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import GuardrailActionKind
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.llm.probe import ModelLimits
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    Message,
    Role,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
)


@dataclass
class TalkativeModel:
    """Answers with one tool call a turn until it is told to conclude."""

    answer_after: int = 3
    turns: int = 0
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
        self.turns += 1
        if self.turns > self.answer_after or not request.tools:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                text="The cause is connection pool exhaustion.",
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tool_calls=(
                ToolCall(
                    id=f"c{self.turns}",
                    name="read_logs",
                    arguments={"selector": f"attempt-{self.turns}"},
                ),
            ),
            finish_reason=FinishReason.TOOL_CALLS,
        )

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        return await self.invoke(request)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        if False:  # pragma: no cover — the loop never streams
            yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)


def _tool(name: str, *, payload: str = "two pods are unhealthy") -> RegisteredTool:
    """Return a registered capability that answers with ``payload``."""

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
    def body(selector: str) -> str:
        """Return the recorded lines for ``selector``."""
        return payload

    found = capability_marker(body)
    assert found is not None
    return found


def _long_session(messages: int) -> Session:
    session = Session(id="s1", objective="Why is checkout returning 503?")
    session.append(Message(role=Role.USER, text=session.objective))
    for index in range(messages):
        session.append(Message(role=Role.ASSISTANT, text=f"Thinking about step {index}. " * 40))
    session.record_evidence(
        EvidenceEntry(
            id="",
            capability="read_logs",
            summary="two pods are unhealthy",
            evidence_type=EvidenceType.LOG,
            source="logs",
            content="a log line",
        )
    )
    return session


class TestCompactionIsDrivenByTheMeasuredWindow:
    def test_a_transcript_under_every_trigger_is_left_alone(self) -> None:
        session = _long_session(4)

        result = compact(session, usable_context_tokens=1_000_000)

        assert not result.compacted
        assert result.messages == tuple(session.transcript)

    def test_a_transcript_over_the_measured_window_is_compacted_early(self) -> None:
        session = _long_session(10)
        assert len(session.transcript) < TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES

        result = compact(session, usable_context_tokens=2_000)

        assert result.compacted
        assert result.strategy == COMPACTION_STRATEGY

    def test_the_message_count_trigger_still_works_without_a_measurement(self) -> None:
        session = _long_session(TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES + 2)

        result = compact(session, usable_context_tokens=0)

        assert result.compacted

    def test_the_objective_and_the_evidence_survive_and_the_rest_is_recorded(self) -> None:
        session = _long_session(30)

        result = compact(session, usable_context_tokens=2_000)

        assert result.messages[0].text == session.objective
        assert "e1" in result.summary
        assert result.dropped
        assert len(result.dropped) == result.removed

    def test_the_most_recent_turns_are_kept_verbatim(self) -> None:
        session = _long_session(30)
        last = session.transcript[-1]

        result = compact(session, usable_context_tokens=2_000)

        assert result.messages[-1] == last


class TestTheRunRecordsWhatItDidToItsOwnContext:
    async def test_a_run_against_a_small_window_completes_with_compaction_in_the_trace(
        self,
    ) -> None:
        model = TalkativeModel(answer_after=4)
        loop = ReActLoop(
            llm=model,
            tools=[_tool("read_logs", payload="a log line from checkout " * 20)],
            limits=ModelLimits(usable_context_tokens=200),
        )

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert result.status is RunStatus.COMPLETED
        compactions = [
            action
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.TRANSCRIPT_COMPACTED
        ]
        assert compactions
        assert COMPACTION_STRATEGY in compactions[0].reason

    async def test_the_narrowing_of_the_schema_set_is_recorded(self) -> None:
        model = TalkativeModel(answer_after=1)
        tools = [_tool(f"read_logs_{index}") for index in range(6)]
        loop = ReActLoop(llm=model, tools=tools, limits=ModelLimits(max_tool_schemas=3))

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert len(model.requests[0].tools) == 3
        narrowings = [
            action
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.SCHEMAS_NARROWED
        ]
        assert narrowings
        assert "3" in narrowings[0].reason

    async def test_an_unmeasured_deployment_offers_everything_it_was_given(self) -> None:
        model = TalkativeModel(answer_after=1)
        tools = [_tool(f"read_logs_{index}") for index in range(6)]
        loop = ReActLoop(llm=model, tools=tools)

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert len(model.requests[0].tools) == 6
        assert not [
            action
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.SCHEMAS_NARROWED
        ]
        assert ModelLimits().max_tool_schemas == MAX_AGENT_TOOL_SCHEMAS

    async def test_an_oversized_result_is_shortened_for_the_model_and_kept_whole(self) -> None:
        payload = "a very long log line\n" * 2_000
        model = TalkativeModel(answer_after=1)
        loop = ReActLoop(
            llm=model,
            tools=[_tool("read_logs", payload=payload)],
            limits=ModelLimits(usable_context_tokens=4_000),
        )

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        shown = [
            item
            for message in result.session.transcript
            for item in message.tool_results
            if item.name == "read_logs"
        ]
        assert shown
        assert len(shown[0].content) < len(payload)
        assert result.session.evidence[0].content == payload
        truncations = [
            action
            for turn in result.session.turns
            for action in turn.guardrail_actions
            if action.kind is GuardrailActionKind.RESULT_TRUNCATED
        ]
        assert truncations

    async def test_an_unmeasured_deployment_shows_the_whole_result(self) -> None:
        payload = "a very long log line\n" * 2_000
        model = TalkativeModel(answer_after=1)
        loop = ReActLoop(llm=model, tools=[_tool("read_logs", payload=payload)])

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        shown = [
            item
            for message in result.session.transcript
            for item in message.tool_results
            if item.name == "read_logs"
        ]
        assert shown[0].content == payload
