"""The layer between the provider adapter and the runtime.

It is a distinct layer for two reasons, and both are about where the alternative
would put the code. Inside the adapter, this would exist nine times and be
invisible to the trace. Inside the ReAct loop, model-behaviour handling would sit
in the middle of a control flow that is about investigating. Here it is one
implementation, keyed off what the model *did* rather than off which provider
served it, and every repair is a value the trace carries.

It satisfies :class:`~core.llm.types.LLMClient`, so wrapping is the whole of the
integration: the loop that was given a provider client is given this instead and
nothing else changes.

**A well-behaved model pays nothing.** Every mechanism here is triggered by a
detected problem. A turn whose tool calls parse, name declared parameters,
supply the required ones and are not a repetition makes exactly one call to the
provider and comes back carrying no repairs at all — which is asserted rather
than claimed, in ``tests/contract/llm/test_overhead_on_the_clean_path.py``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from config.constants.llm import MODEL_CALL_BUDGET_SECONDS
from config.prompts.resilience import (
    CALL_BUDGET_EXCEEDED,
    NO_CALL_CORRECTION,
    REPAIR_BUDGET_EXHAUSTED,
    REPETITION_BREAK,
    UNREADABLE_CALL_CORRECTION,
)
from core.llm.failures import FailureClass
from core.llm.resilience.arguments import check_arguments, correction_for, signature
from core.llm.resilience.bounds import RepairBudget
from core.llm.resilience.extraction import assemble_fragments, extract_tool_call
from core.llm.resilience.loops import RepetitionDetector
from core.llm.resilience.recorder import NO_RECORDER, RepairRecorder
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    LLMClient,
    Message,
    Repair,
    RepairKind,
    Role,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
    ToolSchema,
)

#: Metadata key the runtime puts a session identifier under. Repetition is
#: counted per session, and a client cached per role is shared by every run in
#: the process, so without this two investigations could add up to a loop in
#: neither of them.
SESSION_METADATA_KEY = "session_id"


class ResilientClient:
    """One provider client, plus what to do when the model gets it wrong."""

    def __init__(
        self,
        inner: LLMClient,
        *,
        endpoint: str = "",
        budget: RepairBudget | None = None,
        detector: RepetitionDetector | None = None,
        recorder: RepairRecorder = NO_RECORDER,
        call_budget_seconds: float = MODEL_CALL_BUDGET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        # A label, never a branch. Nothing in this layer reads it to decide
        # anything; it is here so a timeout can say which endpoint hung.
        self._endpoint = endpoint or inner.provider_id
        self._budget = budget or RepairBudget()
        self._detector = detector or RepetitionDetector()
        self._recorder = recorder
        self._call_budget = call_budget_seconds
        self._clock = clock

    # -- identity -------------------------------------------------------------

    @property
    def provider_id(self) -> str:
        """Return the provider the wrapped client speaks to."""
        return self._inner.provider_id

    @property
    def model_id(self) -> str:
        """Return the model the wrapped client is bound to."""
        return self._inner.model_id

    @property
    def inner(self) -> LLMClient:
        """Return the client this layer wraps."""
        return self._inner

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the wrapped client's estimate, unchanged."""
        return self._inner.count_tokens(request)

    # -- one turn -------------------------------------------------------------

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return one usable turn, or a partial result naming what stopped it.

        Loops only while a correction has been sent and the budget allowed it.
        The loop's exit is the budget, so a model that cannot be corrected costs
        a bounded number of calls and then degrades with its behaviour named.
        """
        self._budget.next_turn()
        session = str(request.metadata.get(SESSION_METADATA_KEY, ""))
        schemas = {schema.name: schema for schema in request.tools}
        repairs: list[Repair] = []
        current = request
        broken_out = False

        while True:
            result = await self._invoke_once(current)
            if not result.succeeded:
                return replace(result, repairs=tuple(repairs))

            calls, found = self._read_calls(result, request.tools)
            repairs.extend(found)

            correction = self._correction_for_calls(calls, schemas, repairs)
            if correction is None:
                verdict = self._detector.observe(session, calls)
                if verdict.repeating and not broken_out:
                    broken_out = True
                    self._detector.forget(session)
                    repairs.append(
                        Repair(
                            kind=RepairKind.REPETITION_BROKEN,
                            capability=verdict.capability,
                            detail=(
                                f"called {verdict.count} times with the same arguments "
                                f"inside a {verdict.window}-turn window"
                            ),
                        )
                    )
                    correction = REPETITION_BREAK.format(
                        capability=verdict.capability,
                        count=verdict.count,
                        window=verdict.window,
                    )
                else:
                    self._count(repairs)
                    return replace(result, tool_calls=calls, repairs=tuple(repairs))

            if not self._budget.spend():
                self._count(repairs)
                return self._degraded(result, repairs)

            current = replace(
                current,
                messages=(*current.messages, Message(role=Role.USER, text=correction)),
            )

    async def _invoke_once(self, request: InvokeRequest) -> InvokeResult:
        """Call the wrapped client inside the per-call time budget.

        The transport already carries a timeout of its own. This is the one that
        holds when that timeout does not — a machine that has started swapping
        under load makes every call take minutes, and a run that hangs there has
        nothing in its trace to say why.
        """
        started = self._clock()
        try:
            return await asyncio.wait_for(self._inner.invoke(request), timeout=self._call_budget)
        except TimeoutError:
            elapsed = self._clock() - started
            self._recorder.record_degradation(
                "call_budget_exceeded", provider_id=self.provider_id, model_id=self.model_id
            )
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                finish_reason=FinishReason.ERROR,
                partial=True,
                failure=FailureClass.TRANSIENT,
                failure_message=CALL_BUDGET_EXCEEDED.format(
                    endpoint=self._endpoint, budget=self._call_budget, elapsed=elapsed
                ),
            )

    # -- reading what the model asked for --------------------------------------

    def _read_calls(
        self, result: InvokeResult, offered: Sequence[ToolSchema]
    ) -> tuple[tuple[ToolCall, ...], list[Repair]]:
        """Return the calls this turn actually contains, and what it cost to find them."""
        repairs: list[Repair] = []
        calls = result.tool_calls

        if not calls and offered and result.text:
            extraction = extract_tool_call(result.text, offered)
            if extraction.call is not None:
                repairs.append(
                    Repair(
                        kind=RepairKind.TOOL_CALL_EXTRACTED,
                        capability=extraction.call.name,
                        detail="the model wrote the call as text rather than emitting one",
                    )
                )
                calls = (extraction.call,)
            elif extraction.named:
                repairs.append(
                    Repair(
                        kind=RepairKind.NO_TOOL_CALL_FOUND,
                        capability=extraction.named,
                        detail="the text named a capability and its arguments could not be read",
                    )
                )

        return self._deduplicated(calls, repairs)

    @staticmethod
    def _deduplicated(
        calls: tuple[ToolCall, ...], repairs: list[Repair]
    ) -> tuple[tuple[ToolCall, ...], list[Repair]]:
        """Return ``calls`` with a repeat of an earlier one in the same turn dropped."""
        seen: set[tuple[str, str]] = set()
        kept: list[ToolCall] = []
        for call in calls:
            key = signature(call)
            if key in seen:
                repairs.append(
                    Repair(
                        kind=RepairKind.DUPLICATE_CALL_DISCARDED,
                        capability=call.name,
                        detail="the same call twice in one turn; the second was not executed",
                    )
                )
                continue
            seen.add(key)
            kept.append(call)
        return tuple(kept), repairs

    def _correction_for_calls(
        self,
        calls: Sequence[ToolCall],
        schemas: Mapping[str, ToolSchema],
        repairs: list[Repair],
    ) -> str | None:
        """Return what the model must be told about these calls, or ``None``.

        The first bad call decides. Reporting all of them at once reads well and
        gives a small model four things to fix in one turn, which is how a
        correction becomes a second malformed call.
        """
        for call in calls:
            schema = schemas.get(call.name)
            if schema is None:
                # A name that was never offered is the provider client's to drop
                # and the runtime's to refuse; repairing it here would be a
                # second opinion on a decision already made.
                continue
            verdict = check_arguments(call, schema)
            if verdict.acceptable:
                continue
            for parameter in verdict.unknown:
                repairs.append(
                    Repair(
                        kind=RepairKind.UNKNOWN_ARGUMENT_REJECTED,
                        capability=call.name,
                        parameter=parameter,
                        detail=f"{call.name} declares no parameter {parameter!r}",
                    )
                )
            for parameter in verdict.missing:
                repairs.append(
                    Repair(
                        kind=RepairKind.MISSING_ARGUMENT_REPORTED,
                        capability=call.name,
                        parameter=parameter,
                        detail=f"{call.name} requires {parameter!r} and the call omitted it",
                    )
                )
            return correction_for(verdict, schema)

        if not calls and any(repair.kind is RepairKind.NO_TOOL_CALL_FOUND for repair in repairs):
            named = next(
                repair.capability
                for repair in reversed(repairs)
                if repair.kind is RepairKind.NO_TOOL_CALL_FOUND
            )
            return (
                UNREADABLE_CALL_CORRECTION.format(capability=named)
                if named
                else NO_CALL_CORRECTION.format(available=", ".join(sorted(schemas)))
            )
        return None

    # -- degrading -------------------------------------------------------------

    def _degraded(self, result: InvokeResult, repairs: Sequence[Repair]) -> InvokeResult:
        """Return the partial result a spent repair budget produces.

        Never an exception, and never a bare "the budget was exhausted": the
        failure names the model, the provider and what the model kept doing, so
        an operator reading it knows the next step is to change model rather than
        to check their network.
        """
        behaviour = ", ".join(
            sorted({repair.kind.value for repair in repairs}) or ["unusable tool calls"]
        )
        self._recorder.record_degradation(
            "repair_budget_exhausted", provider_id=self.provider_id, model_id=self.model_id
        )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            finish_reason=FinishReason.ERROR,
            usage=result.usage,
            attempts=result.attempts,
            degradations=result.degradations,
            repairs=tuple(repairs),
            partial=True,
            failure=FailureClass.MODEL_BEHAVIOUR,
            failure_message=REPAIR_BUDGET_EXHAUSTED.format(
                model=self.model_id,
                provider=self.provider_id,
                attempts=len(repairs),
                behaviour=behaviour,
            ),
        )

    def _count(self, repairs: Sequence[Repair]) -> None:
        """Offer every repair to the recorder, once."""
        for repair in repairs:
            self._recorder.record_repair(
                repair, provider_id=self.provider_id, model_id=self.model_id
            )

    # -- the rest of the surface ------------------------------------------------

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result, with the call held to its time budget.

        The structured-output ladder lives in the provider client and is not
        repaired here: its fallbacks already read whatever the model wrote, which
        is the same job this layer does for tool calls.
        """
        try:
            return await asyncio.wait_for(
                self._inner.invoke_structured(request, schema), timeout=self._call_budget
            )
        except TimeoutError:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                finish_reason=FinishReason.ERROR,
                partial=True,
                failure=FailureClass.TRANSIENT,
                failure_message=CALL_BUDGET_EXCEEDED.format(
                    endpoint=self._endpoint, budget=self._call_budget, elapsed=self._call_budget
                ),
            )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Yield the wrapped client's events, with fragmented calls put together.

        A provider that streams a tool call's arguments as text deltas emits a
        sequence of pieces that are meaningless apart. They are buffered by call
        identifier and released as one assembled call; every other event passes
        through untouched, so a stream with no fragments in it is the stream the
        inner client produced.
        """
        names: dict[str, str] = {}
        fragments: dict[str, list[str]] = {}

        async for event in self._inner.stream(request):
            if event.kind is StreamEventKind.TOOL_CALL and event.tool_call_fragment:
                call_id = event.tool_call.id if event.tool_call else ""
                if event.tool_call and event.tool_call.name:
                    names[call_id] = event.tool_call.name
                fragments.setdefault(call_id, []).append(event.tool_call_fragment)
                continue
            if event.kind in {StreamEventKind.FINISH, StreamEventKind.ERROR}:
                for assembled in self._assembled(names, fragments):
                    yield assembled
                fragments.clear()
            yield event

        for assembled in self._assembled(names, fragments):
            yield assembled

    def _assembled(
        self, names: Mapping[str, str], fragments: Mapping[str, list[str]]
    ) -> list[StreamEvent]:
        """Return one event per buffered call whose fragments add up to a document."""
        events: list[StreamEvent] = []
        for call_id, pieces in fragments.items():
            call = assemble_fragments(names.get(call_id, ""), pieces, call_id=call_id)
            if call is None:
                continue
            self._recorder.record_repair(
                Repair(
                    kind=RepairKind.FRAGMENTS_REASSEMBLED,
                    capability=call.name,
                    detail=f"{len(pieces)} fragments",
                ),
                provider_id=self.provider_id,
                model_id=self.model_id,
            )
            events.append(StreamEvent(kind=StreamEventKind.TOOL_CALL, tool_call=call))
        return events


__all__ = ["SESSION_METADATA_KEY", "ResilientClient"]
