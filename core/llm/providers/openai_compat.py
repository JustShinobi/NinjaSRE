"""The OpenAI chat-completions wire, shared by five of the nine providers.

OpenAI, Azure OpenAI, OpenRouter, NVIDIA NIM, and Ollama/vLLM all speak this
wire. One translation covers all five, and the differences between them are
capability flags rather than code: whether structured output is native, whether
parallel tool calls survive, whether reasoning effort means anything.

The differences that *are* code live in the subclasses, and there are only
three: Azure addresses a deployment instead of a model, OpenRouter passes
reasoning controls through under its own key, and Ollama has to serialise tool
calls because its models produce nonsense when asked for several at once.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.llm import (
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)
from core.llm.cache import CachePlan
from core.llm.failures import ErrorObservation
from core.llm.providers.base import BaseAdapter, ParsedResponse, coerce_tool_arguments
from core.llm.registry import ModelDescriptor
from core.llm.structured.native import WireFamily, native_request_fields
from core.llm.types import (
    Degradation,
    DegradationKind,
    FinishReason,
    InvokeRequest,
    Message,
    Role,
    StreamEvent,
    StreamEventKind,
    ToolCall,
)
from core.llm.usage import TokenCounts

_FINISH_REASONS: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
    "refusal": FinishReason.REFUSAL,
}


def _tool_definitions(request: InvokeRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            },
        }
        for tool in request.tools
    ]


def _assistant_message(message: Message) -> dict[str, Any]:
    """Return an assistant turn, with tool calls in the wire's shape."""
    body: dict[str, Any] = {"role": "assistant", "content": message.text or None}
    if message.tool_calls:
        body["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    # The wire carries arguments as a JSON *string*, not an
                    # object. Sending an object is accepted by some
                    # implementations and rejected by others, which is exactly
                    # the kind of difference that only shows up in production.
                    "arguments": json.dumps(dict(call.arguments), sort_keys=True),
                },
            }
            for call in message.tool_calls
        ]
    return body


def _messages(request: InvokeRequest) -> list[dict[str, Any]]:
    """Return the conversation in wire order, system prompt first."""
    body: list[dict[str, Any]] = []
    if request.system:
        body.append({"role": "system", "content": request.system})

    for message in request.messages:
        if message.role is Role.ASSISTANT:
            body.append(_assistant_message(message))
            continue
        if message.tool_results:
            # Each result is its own message on this wire, keyed by call id.
            for result in message.tool_results:
                body.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": result.content,
                    }
                )
            if message.text:
                body.append({"role": "user", "content": message.text})
            continue
        body.append({"role": message.role.value, "content": message.text})
    return body


def _parse_usage(document: Mapping[str, Any]) -> TokenCounts:
    """Return the token counts from an OpenAI-wire ``usage`` block.

    ``prompt_tokens`` on this wire *includes* cached tokens, unlike the neutral
    model where the three input fields are disjoint. Subtracting here is what
    keeps a cached run from looking more expensive than an uncached one.
    """
    usage = document.get("usage")
    if not isinstance(usage, Mapping):
        return TokenCounts(estimated=True)

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)

    prompt_details = usage.get("prompt_tokens_details")
    cached = 0
    if isinstance(prompt_details, Mapping):
        cached = int(prompt_details.get("cached_tokens") or 0)

    completion_details = usage.get("completion_tokens_details")
    reasoning = 0
    if isinstance(completion_details, Mapping):
        reasoning = int(completion_details.get("reasoning_tokens") or 0)

    return TokenCounts(
        input_tokens=max(prompt_tokens - cached, 0),
        output_tokens=completion_tokens,
        cached_input_tokens=cached,
        reasoning_tokens=reasoning,
    )


def _parse_tool_calls(message: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    raw = message.get("tool_calls")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return ()

    calls: list[ToolCall] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            continue
        function = entry.get("function")
        if not isinstance(function, Mapping):
            continue
        name = str(function.get("name") or "")
        if not name:
            continue
        calls.append(
            ToolCall(
                id=str(entry.get("id") or f"call_{index}"),
                name=name,
                arguments=coerce_tool_arguments(function.get("arguments")),
            )
        )
    return tuple(calls)


class OpenAiCompatibleAdapter(BaseAdapter):
    """Translates the neutral vocabulary to and from the OpenAI chat wire."""

    provider_identifier = PROVIDER_OPENAI
    wire = WireFamily.OPENAI

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the chat-completions body for ``request``."""
        payload: dict[str, Any] = {
            "model": descriptor.wire_model_id,
            "messages": _messages(request),
        }

        if request.tools:
            payload["tools"] = _tool_definitions(request)
            if not request.parallel_tool_calls or not descriptor.supports_parallel_tool_calls:
                payload["parallel_tool_calls"] = False
            if request.force_tool_call:
                # Obliges the model to call one of the declared tools — the
                # preflight probe's own way of finding out whether tool calling
                # actually works, rather than whether the model is willing to.
                payload["tool_choice"] = "required"

        max_output = request.max_output_tokens or descriptor.max_output_tokens
        payload["max_completion_tokens"] = max_output

        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)

        if request.response_schema is not None and descriptor.supports_structured_output:
            payload.update(
                native_request_fields(request.response_schema, self.dialect, self.wire_family)
            )

        self._apply_reasoning(payload, request, descriptor)
        self._apply_cache(payload, cache)
        return payload

    def _apply_reasoning(
        self,
        payload: dict[str, Any],
        request: InvokeRequest,
        descriptor: ModelDescriptor,
    ) -> None:
        """Add the reasoning control, where the model has one."""
        if request.reasoning_effort is None or not descriptor.supports_reasoning_effort:
            return
        payload["reasoning_effort"] = request.reasoning_effort.value

    def _apply_cache(self, payload: dict[str, Any], cache: CachePlan) -> None:
        """Apply prompt caching.

        This wire caches automatically on a matching prefix; there is no marker
        to place, which is why the plan is consulted and then does nothing here.
        """

    def parse_response(
        self, document: Mapping[str, Any], descriptor: ModelDescriptor
    ) -> ParsedResponse:
        """Return the chat-completions document read into neutral terms."""
        choices = document.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            return ParsedResponse(
                finish_reason=FinishReason.ERROR,
                tokens=_parse_usage(document),
                degradations=(
                    Degradation(DegradationKind.USAGE_ESTIMATED, "response carried no choices"),
                ),
            )

        choice = choices[0]
        message = choice.get("message") if isinstance(choice, Mapping) else None
        message = message if isinstance(message, Mapping) else {}

        raw_finish = (
            str(choice.get("finish_reason") or "stop") if isinstance(choice, Mapping) else "stop"
        )
        tool_calls = _parse_tool_calls(message)
        finish_reason = _FINISH_REASONS.get(raw_finish, FinishReason.STOP)
        if tool_calls and finish_reason is FinishReason.STOP:
            finish_reason = FinishReason.TOOL_CALLS

        content = message.get("content")
        text = content if isinstance(content, str) else ""

        tokens = _parse_usage(document)
        degradations: tuple[Degradation, ...] = ()
        if tokens.estimated:
            degradations = (
                Degradation(DegradationKind.USAGE_ESTIMATED, "provider omitted the usage block"),
            )

        return ParsedResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            tokens=tokens,
            degradations=degradations,
        )

    def parse_stream_chunk(self, chunk: Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        """Return the events one streamed chunk carries."""
        events: list[StreamEvent] = []

        choices = chunk.get("choices")
        if isinstance(choices, Sequence) and choices:
            choice = choices[0]
            if isinstance(choice, Mapping):
                delta = choice.get("delta")
                if isinstance(delta, Mapping):
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        events.append(StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=content))
                    for call in _parse_tool_calls(delta):
                        events.append(StreamEvent(kind=StreamEventKind.TOOL_CALL, tool_call=call))
                finish = choice.get("finish_reason")
                if isinstance(finish, str) and finish:
                    events.append(
                        StreamEvent(
                            kind=StreamEventKind.FINISH,
                            finish_reason=_FINISH_REASONS.get(finish, FinishReason.STOP),
                        )
                    )

        if isinstance(chunk.get("usage"), Mapping):
            events.append(StreamEvent(kind=StreamEventKind.USAGE))

        return tuple(events)

    def observe_error(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return the neutral reading of an OpenAI-wire error document."""
        error = document.get("error")
        error = error if isinstance(error, Mapping) else document
        return ErrorObservation(
            status_code=status_code,
            error_code=str(error.get("code") or error.get("type") or "") or None,
            message=str(error.get("message") or ""),
            body=dict(document),
        )


class OpenAiAdapter(OpenAiCompatibleAdapter):
    """OpenAI itself."""

    provider_identifier = PROVIDER_OPENAI


class OpenRouterAdapter(OpenAiCompatibleAdapter):
    """OpenRouter, an aggregator whose upstreams vary per route."""

    provider_identifier = PROVIDER_OPENROUTER

    def _apply_reasoning(
        self,
        payload: dict[str, Any],
        request: InvokeRequest,
        descriptor: ModelDescriptor,
    ) -> None:
        """Pass the reasoning control through OpenRouter's own key.

        OpenRouter forwards this to whichever upstream serves the route, and
        ignores it where the upstream has no such control — which is exactly the
        explicit-degradation behaviour the abstraction wants.
        """
        if request.reasoning_effort is None or not descriptor.supports_reasoning_effort:
            return
        payload["reasoning"] = {"effort": request.reasoning_effort.value}


class NvidiaNimAdapter(OpenAiCompatibleAdapter):
    """NVIDIA NIM, self-hostable and OpenAI-wire compatible."""

    provider_identifier = PROVIDER_NVIDIA_NIM


class OllamaAdapter(OpenAiCompatibleAdapter):
    """Ollama and vLLM, serving local models over the OpenAI wire."""

    provider_identifier = PROVIDER_OLLAMA

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the body, with parallel tool calls always off.

        Not a capability flag but a correctness one: asked for several tool
        calls at once, a quantised model reliably produces a single malformed
        one. Serialising is slower and works.
        """
        payload = super().build_payload(request, descriptor, cache)
        if request.tools:
            payload["parallel_tool_calls"] = False
        return payload


__all__ = [
    "NvidiaNimAdapter",
    "OllamaAdapter",
    "OpenAiAdapter",
    "OpenAiCompatibleAdapter",
    "OpenRouterAdapter",
]
