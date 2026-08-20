"""Doubles the runtime-composition tests drive ``ReActLoop`` with.

Self-contained rather than importing ``tests/unit/core/agent/conftest.py``:
that module is not a package these tests can import across a directory
boundary, and the two doubles this file needs are small enough that copying
the shape is cheaper than wiring a cross-directory import.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

import pytest

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.llm.types import FinishReason, InvokeRequest, InvokeResult, StreamEvent, TokenEstimate
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


def failed_turn(message: str = "provider unavailable") -> InvokeResult:
    """Return the shape a provider hands back when a call did not land.

    A soft failure — a normal return, not a raised exception — is how this
    codebase's ``LLMClient`` implementations report an unreachable model; the
    loop is what turns enough of these into a ``RunResult`` whose status is
    ``FAILED``.
    """
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
    """An ``LLMClient`` that returns the turns a test wrote down, in order."""

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
        raise NotImplementedError("these tests do not stream")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result for one turn."""
        return await self.invoke(request)

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a character-count estimate of ``request``."""
        characters = len(request.system or "") + sum(
            len(message.text) for message in request.messages
        )
        return TokenEstimate(tokens=characters // 4, estimated=True)


def fixture_tool(name: str) -> RegisteredTool:
    """Return a throwaway ``RegisteredTool`` named ``name``, for catalogue tests.

    A distinct Python function per call — the ``@tool`` decorator keys its
    metadata off the function it wraps, and two tools sharing one function
    object would collide.
    """

    def _body() -> dict[str, Any]:
        return {"ok": True}

    _body.__name__ = f"fixture_tool_{name}"
    decorated = tool(
        name=name,
        display_name=name.replace("_", " ").title(),
        description=f"Throwaway fixture capability {name!r}.",
        domain="observability",
        evidence_source="fixture",
        evidence_type=EvidenceType.EVENT,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )(_body)
    found = capability_marker(decorated)
    assert found is not None, f"{name!r} carries no capability marker"
    return found


@pytest.fixture
def scripted_llm() -> ScriptedLLM:
    """Return an ``LLMClient`` double that never makes a network call."""
    return ScriptedLLM([text_turn("diagnosis: the disk on host-1 is full")])
