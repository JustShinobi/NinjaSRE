"""Doubles the loop tests drive the runtime with.

Two of them, and both are deliberately dumb. A scripted model returns the turns
a fixture wrote down; a recording tool counts its calls. Neither knows anything
about the loop, which is the point: every assertion in these tests is about the
loop's control flow rather than about a mock that was taught to agree with it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    TokenEstimate,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord

PROVIDER_ID = "fixture"
MODEL_ID = "scripted-1"


def text_turn(text: str) -> InvokeResult:
    """Return a model turn that concludes in prose."""
    return InvokeResult(
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        text=text,
        finish_reason=FinishReason.STOP,
        usage=UsageRecord(
            provider_id=PROVIDER_ID,
            model_id=MODEL_ID,
            tokens=TokenCounts(input_tokens=100, output_tokens=20),
        ),
    )


def call_turn(*calls: ToolCall, text: str = "") -> InvokeResult:
    """Return a model turn that requests ``calls``."""
    return InvokeResult(
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        text=text,
        tool_calls=calls,
        finish_reason=FinishReason.TOOL_CALLS,
        usage=UsageRecord(
            provider_id=PROVIDER_ID,
            model_id=MODEL_ID,
            tokens=TokenCounts(input_tokens=100, output_tokens=20),
        ),
    )


def failed_turn(message: str = "provider unavailable") -> InvokeResult:
    """Return the shape ``ProviderClient`` hands back when a call did not land."""
    from core.llm.failures import FailureClass

    return InvokeResult(
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        finish_reason=FinishReason.ERROR,
        partial=True,
        failure=FailureClass.MODEL_UNAVAILABLE,
        failure_message=message,
    )


class ScriptedLLM:
    """An ``LLMClient`` that returns the turns a fixture wrote down.

    Once the script runs out the last entry repeats, so a fixture that means
    "the model keeps asking for the same thing forever" is one line rather than
    twenty — which is exactly the pathological case the iteration ceiling
    exists for.
    """

    def __init__(
        self,
        turns: Sequence[InvokeResult] | Callable[[InvokeRequest], InvokeResult],
        *,
        repeat_last: bool = True,
    ) -> None:
        self._turns = turns
        self._repeat_last = repeat_last
        self.requests: list[InvokeRequest] = []

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""
        return PROVIDER_ID

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""
        return MODEL_ID

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the next scripted turn."""
        self.requests.append(request)
        if callable(self._turns):
            return self._turns(request)
        index = len(self.requests) - 1
        if index < len(self._turns):
            return self._turns[index]
        if self._repeat_last and self._turns:
            return self._turns[-1]
        return text_turn("nothing further to add")

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Return an iterator of events for one streamed turn."""
        raise NotImplementedError("the loop does not stream")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result for one turn."""
        return await self.invoke(request)

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a character-count estimate of ``request``."""
        characters = len(request.system or "") + sum(
            len(message.text)
            + sum(len(result.content) for result in message.tool_results)
            + sum(len(str(dict(call.arguments))) for call in message.tool_calls)
            for message in request.messages
        )
        return TokenEstimate(tokens=characters // 4, estimated=True)


def registration(function: Any) -> RegisteredTool:
    """Return the registration a decorated function carries."""
    found = capability_marker(function)
    assert found is not None, f"{function!r} carries no capability marker"
    return found


class CallCounter:
    """Counts what a fixture tool was asked to do, without a mocking library."""

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def record(self, **arguments: Any) -> None:
        """Note one invocation."""
        self.calls.append(dict(arguments))

    @property
    def count(self) -> int:
        """Return how many times the tool ran."""
        return len(self.calls)


@tool(
    name="fixture_log_search",
    display_name="Fixture log search",
    description="Return a canned count of matching log lines.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.LOG,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def fixture_log_search(query: str) -> dict[str, Any]:
    """Return a canned aggregate for ``query``."""
    return {"query": query, "matches": 412}


@tool(
    name="fixture_metric_read",
    display_name="Fixture metric read",
    description="Return a canned time series.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def fixture_metric_read(series: str) -> dict[str, Any]:
    """Return a canned reading for ``series``."""
    return {"series": series, "value": 0.93}


@tool(
    name="fixture_serial_probe",
    display_name="Fixture serial probe",
    description="A capability whose author says it must not run alongside another.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=False,
)
def fixture_serial_probe(target: str) -> dict[str, Any]:
    """Return a canned probe result for ``target``."""
    return {"target": target, "reachable": True}


@tool(
    name="fixture_always_fails",
    display_name="Fixture failing tool",
    description="Always raises, so a partial batch has something to fail on.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def fixture_always_fails() -> dict[str, Any]:
    """Raise, always."""
    raise ConnectionError("the fixture upstream is down")


@tool(
    name="fixture_slow_read",
    display_name="Fixture slow read",
    description="Sleeps, so a latency assertion has something to measure.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
async def fixture_slow_read(target: str, delay_seconds: float = 0.05) -> dict[str, Any]:
    """Return ``target`` after ``delay_seconds``."""
    import asyncio

    await asyncio.sleep(delay_seconds)
    return {"target": target}


@tool(
    name="fixture_blocking_read",
    display_name="Fixture blocking read",
    description="A synchronous body that sleeps, as a vendor SDK's client does.",
    domain="observability",
    evidence_source="fixture",
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def fixture_blocking_read(target: str, delay_seconds: float = 0.05) -> dict[str, Any]:
    """Return ``target`` after blocking the calling thread for ``delay_seconds``."""
    import time

    time.sleep(delay_seconds)
    return {"target": target}


@tool(
    name="fixture_reasoning_note",
    display_name="Fixture reasoning note",
    description="Record a line of the agent's own reasoning.",
    domain="methodology",
    evidence_source=EvidenceSource.REASONING,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def fixture_reasoning_note(note: str) -> dict[str, Any]:
    """Return ``note`` unchanged."""
    return {"note": note}


LOG_SEARCH = registration(fixture_log_search)
METRIC_READ = registration(fixture_metric_read)
SERIAL_PROBE = registration(fixture_serial_probe)
ALWAYS_FAILS = registration(fixture_always_fails)
SLOW_READ = registration(fixture_slow_read)
BLOCKING_READ = registration(fixture_blocking_read)
REASONING_NOTE = registration(fixture_reasoning_note)

DEFAULT_TOOLS: tuple[RegisteredTool, ...] = (LOG_SEARCH, METRIC_READ, SERIAL_PROBE, ALWAYS_FAILS)


def log_call(identifier: str, query: str = "service:checkout status:500") -> ToolCall:
    """Return a model request to run the fixture log search."""
    return ToolCall(id=identifier, name="fixture_log_search", arguments={"query": query})
