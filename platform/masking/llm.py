"""The boundary itself: one wrapper, and nothing above it knows masking exists.

Masking applies at exactly one place — the moment a request stops being an
object in the operator's process and becomes bytes addressed to somebody else's
service. This module is that place. It is a decorator over ``LLMClient`` rather
than a change inside ``core/llm/`` for two reasons that are the same reason:
``core/llm/`` is nine adapters and one client, and a control that had to be
added to each of them would eventually be missing from one; and the masking
policy is a platform concern that the provider layer should not have to know
about to stay provider-neutral.

The wrapper is symmetric. Requests go out masked; results come back restored —
text, tool-call arguments, and structured fields alike. So the agent loop, the
capabilities, and the pipeline all deal in real pod names and cluster names,
and the *only* code that ever sees a token is the code on the far side of this
file. That is what makes "masking must not alter text the model has to
reproduce exactly" hold without a special case: nothing downstream has to
reproduce a token, because nothing downstream ever receives one.

Streaming is the part with a real trap in it. A token is split across event
boundaries whenever the provider feels like it, so restoring per event would
emit ``NSRE_MASK_`` and ``POD_1`` as two unresolvable halves. The stream holds
back any tail that could still turn into a token, and flushes at the end.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import replace
from typing import Any

from config.constants.security import MASK_TOKEN_PREFIX
from core.llm.types import (
    InvokeRequest,
    InvokeResult,
    LLMClient,
    Message,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
)
from platform.masking.context import MaskingContext

#: The longest token ``mapping.py`` can issue: prefix, a label, the separator,
#: and an ordinal. The stream holds back at most this much.
_MAX_TOKEN_LENGTH = len(MASK_TOKEN_PREFIX) + 64 + 1 + 6

#: Matches a tail that might still become a token — either a partial prefix or
#: a complete prefix whose ordinal has not finished arriving. Anchored at the
#: end and only ever run against the last ``_MAX_TOKEN_LENGTH`` characters, so
#: the cost per event is constant rather than proportional to the buffer.
_INCOMPLETE_TOKEN_TAIL: re.Pattern[str] = re.compile(
    "(?:"
    + "|".join(
        re.escape(MASK_TOKEN_PREFIX[:length]) for length in range(len(MASK_TOKEN_PREFIX) - 1, 0, -1)
    )
    + "|"
    + re.escape(MASK_TOKEN_PREFIX)
    + r"[A-Z0-9_]{0,71}"
    + ")$"
)


class MaskingLLMClient:
    """An ``LLMClient`` that masks on the way out and restores on the way back.

    Substitutable for the client it wraps — same protocol, same four methods —
    so wiring it in is a line in the factory and removing it is the ablation.
    """

    __slots__ = ("_context", "_inner")

    def __init__(self, *, inner: LLMClient, context: MaskingContext) -> None:
        self._inner = inner
        # Resolved once, here, because a client is bound to one provider for
        # its whole life. ``local_models_exempt`` therefore costs one lookup
        # per client rather than one per call.
        self._context = context.for_provider(inner.provider_id)

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""
        return self._inner.provider_id

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""
        return self._inner.model_id

    @property
    def masking(self) -> MaskingContext:
        """Return the resolved context, for a trace line or an assertion."""
        return self._context

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the result of one turn, masked outbound and restored inbound."""
        result = await self._inner.invoke(self._mask_request(request))
        return self._restore_result(result)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Yield the events of one streamed turn, with tokens restored across them."""
        pending = ""
        async for event in self._inner.stream(self._mask_request(request)):
            if event.kind is not StreamEventKind.TEXT_DELTA:
                # A tool call or a finish means no more text is coming to
                # complete a held-back tail, so flush it before the event that
                # ends the text — out of order would reorder the answer.
                if pending:
                    yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=self._restore(pending))
                    pending = ""
                yield self._restore_event(event)
                continue

            pending += event.text
            emit, pending = _split_at_safe_boundary(pending)
            if emit:
                yield replace(event, text=self._restore(emit))

        if pending:
            yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=self._restore(pending))

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result, restored field by field.

        The schema is not masked. It is NinjaSRE's own document, it contains no
        identifier, and rewriting it would change the contract the provider was
        asked to satisfy.
        """
        result = await self._inner.invoke_structured(self._mask_request(request), schema)
        return self._restore_result(result)

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the cost of the request *as it will be sent*.

        Masked, because that is the string the provider bills for. Counting the
        unmasked request would put the context guard's arithmetic a few percent
        out on every turn, always in the direction that overruns.
        """
        return self._inner.count_tokens(self._mask_request(request))

    # -- outbound -------------------------------------------------------------

    def _mask_request(self, request: InvokeRequest) -> InvokeRequest:
        """Return ``request`` with every identifier in it replaced by a token."""
        if not self._context.active:
            return request
        return replace(
            request,
            system=None if request.system is None else self._context.mask(request.system),
            messages=tuple(self._mask_message(message) for message in request.messages),
        )

    def _mask_message(self, message: Message) -> Message:
        """Return ``message`` with its text, arguments, and results masked."""
        return replace(
            message,
            text=self._context.mask(message.text),
            tool_calls=tuple(
                replace(call, arguments=_walk(call.arguments, self._context.mask))
                for call in message.tool_calls
            ),
            tool_results=tuple(
                replace(result, content=self._context.mask(result.content))
                for result in message.tool_results
            ),
        )

    # -- inbound --------------------------------------------------------------

    def _restore(self, text: str) -> str:
        return self._context.unmask(text)

    def _restore_result(self, result: InvokeResult) -> InvokeResult:
        """Return ``result`` with every token this run issued turned back."""
        if not self._context.active or not len(self._context.mapping):
            return result
        return replace(
            result,
            text=self._restore(result.text),
            tool_calls=tuple(self._restore_call(call) for call in result.tool_calls),
            structured=(
                None if result.structured is None else _walk(result.structured, self._restore)
            ),
        )

    def _restore_call(self, call: ToolCall) -> ToolCall:
        """Return ``call`` with real identifiers in its arguments.

        This is the one that matters operationally. A token reaching a
        capability would be sent to the cluster as a pod name, and the cluster
        would answer, correctly, that no such pod exists.
        """
        return replace(call, arguments=_walk(call.arguments, self._restore))

    def _restore_event(self, event: StreamEvent) -> StreamEvent:
        """Return a non-text event with its tool call restored."""
        if event.tool_call is None:
            return event
        return replace(event, tool_call=self._restore_call(event.tool_call))


def _split_at_safe_boundary(buffered: str) -> tuple[str, str]:
    """Return the prefix that can be emitted and the tail that must be held.

    The tail is whatever could still grow into a token. Everything before it is
    final, so a stream stays a stream — the consumer is not made to wait for the
    end of the answer to see the beginning of it.
    """
    window = buffered[-_MAX_TOKEN_LENGTH:]
    match = _INCOMPLETE_TOKEN_TAIL.search(window)
    if match is None:
        return buffered, ""
    boundary = len(buffered) - (len(window) - match.start())
    return buffered[:boundary], buffered[boundary:]


def _walk(value: Any, transform: Callable[[str], str]) -> Any:
    """Return ``value`` with ``transform`` applied to every string inside it.

    Exhaustive rather than schema-aware, for the same reason the credential
    suite's scanner is: the field somebody adds next week is the one a
    schema-aware walk would miss.
    """
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, Mapping):
        return {
            transform(key) if isinstance(key, str) else key: _walk(item, transform)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_walk(item, transform) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item, transform) for item in value)
    return value


__all__ = ["MaskingLLMClient"]
