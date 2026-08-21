"""The Anthropic Messages wire, and the reference implementation.

Reference because it is the one provider with all of it: native tool calling,
native structured output, streaming, prompt caching with explicit markers, and a
reasoning-effort control. Every other adapter is measured against what this one
does, and the contract suite was written here first.

Two shapes differ from the OpenAI wire in ways that matter. The system prompt is
its own top-level field rather than a message, and tool results are content
blocks inside a user turn rather than messages of their own. Both are handled
here so nothing above this file has to know.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.llm import PROVIDER_ANTHROPIC
from core.llm.cache import CachePlan
from core.llm.failures import ErrorObservation
from core.llm.providers.base import BaseAdapter, ParsedResponse
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

_STOP_REASONS: dict[str, FinishReason] = {
    "end_turn": FinishReason.STOP,
    "stop_sequence": FinishReason.STOP,
    "tool_use": FinishReason.TOOL_CALLS,
    "max_tokens": FinishReason.LENGTH,
    "refusal": FinishReason.REFUSAL,
    "model_context_window_exceeded": FinishReason.LENGTH,
}

_CACHE_MARKER = {"type": "ephemeral"}


def _content_blocks(message: Message) -> list[dict[str, Any]]:
    """Return one message's content as this wire's block list."""
    blocks: list[dict[str, Any]] = []

    for result in message.tool_results:
        blocks.append(
            {
                "type": "tool_result",
                "tool_use_id": result.call_id,
                "content": result.content,
                "is_error": result.is_error,
            }
        )

    if message.text:
        blocks.append({"type": "text", "text": message.text})

    for call in message.tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": dict(call.arguments),
            }
        )

    return blocks


def _parse_usage(document: Mapping[str, Any]) -> TokenCounts:
    """Return the token counts from an Anthropic ``usage`` block.

    ``input_tokens`` here is already the uncached remainder, so unlike the
    OpenAI wire nothing has to be subtracted — the three fields are disjoint,
    which is also how the neutral model defines them.
    """
    usage = document.get("usage")
    if not isinstance(usage, Mapping):
        return TokenCounts(estimated=True)

    return TokenCounts(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cached_input_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
    )


class AnthropicAdapter(BaseAdapter):
    """Translates the neutral vocabulary to and from the Messages wire."""

    provider_identifier = PROVIDER_ANTHROPIC
    wire = WireFamily.ANTHROPIC

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the Messages body for ``request``."""
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                continue
            role = "assistant" if message.role is Role.ASSISTANT else "user"
            blocks = _content_blocks(message)
            if blocks:
                messages.append({"role": role, "content": blocks})

        payload: dict[str, Any] = {
            "model": descriptor.wire_model_id,
            "messages": messages,
            "max_tokens": request.max_output_tokens or descriptor.max_output_tokens,
        }

        if request.system:
            system_block: dict[str, Any] = {"type": "text", "text": request.system}
            if cache.enabled and cache.mark_system:
                system_block["cache_control"] = dict(_CACHE_MARKER)
            payload["system"] = [system_block]

        if request.tools:
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": dict(tool.parameters),
                }
                for tool in request.tools
            ]
            # The marker goes on the *last* tool: it closes the prefix that
            # holds the whole tool block, which is the part that stays byte
            # identical for an entire investigation.
            if cache.enabled and cache.mark_system and tools:
                tools[-1]["cache_control"] = dict(_CACHE_MARKER)
            payload["tools"] = tools
            if not request.parallel_tool_calls or not descriptor.supports_parallel_tool_calls:
                payload["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}

        if cache.enabled and cache.mark_last_message and messages:
            last_blocks = messages[-1]["content"]
            if isinstance(last_blocks, list) and last_blocks:
                last_blocks[-1]["cache_control"] = dict(_CACHE_MARKER)

        if request.stop_sequences:
            payload["stop_sequences"] = list(request.stop_sequences)

        if request.reasoning_effort is not None and descriptor.supports_reasoning_effort:
            payload["output_config"] = {"effort": request.reasoning_effort.value}

        if request.response_schema is not None and descriptor.supports_structured_output:
            fields = native_request_fields(request.response_schema, self.dialect, self.wire_family)
            output_config = payload.setdefault("output_config", {})
            if isinstance(output_config, dict):
                output_config.update(fields.get("output_config", {}))

        return payload

    def parse_response(
        self, document: Mapping[str, Any], descriptor: ModelDescriptor
    ) -> ParsedResponse:
        """Return the Messages document read into neutral terms."""
        blocks = document.get("content")
        blocks = blocks if isinstance(blocks, Sequence) and not isinstance(blocks, str) else []

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            kind = block.get("type")
            if kind == "text":
                value = block.get("text")
                if isinstance(value, str):
                    text_parts.append(value)
            elif kind == "tool_use":
                arguments = block.get("input")
                tool_calls.append(
                    ToolCall(
                        id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
                    )
                )

        raw_stop = str(document.get("stop_reason") or "end_turn")
        finish_reason = _STOP_REASONS.get(raw_stop, FinishReason.STOP)
        if tool_calls and finish_reason is FinishReason.STOP:
            finish_reason = FinishReason.TOOL_CALLS

        tokens = _parse_usage(document)
        degradations: tuple[Degradation, ...] = ()
        if tokens.estimated:
            degradations = (
                Degradation(DegradationKind.USAGE_ESTIMATED, "provider omitted the usage block"),
            )

        return ParsedResponse(
            text="".join(text_parts),
            tool_calls=tuple(tool_calls),
            finish_reason=finish_reason,
            tokens=tokens,
            degradations=degradations,
        )

    def parse_stream_chunk(self, chunk: Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        """Return the events one streamed event carries."""
        kind = chunk.get("type")

        if kind == "content_block_delta":
            delta = chunk.get("delta")
            if isinstance(delta, Mapping) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return (StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=text),)
            return ()

        if kind == "content_block_start":
            block = chunk.get("content_block")
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                arguments = block.get("input")
                return (
                    StreamEvent(
                        kind=StreamEventKind.TOOL_CALL,
                        tool_call=ToolCall(
                            id=str(block.get("id") or ""),
                            name=str(block.get("name") or ""),
                            arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
                        ),
                    ),
                )
            return ()

        if kind == "message_delta":
            delta = chunk.get("delta")
            stop = delta.get("stop_reason") if isinstance(delta, Mapping) else None
            if isinstance(stop, str) and stop:
                return (
                    StreamEvent(
                        kind=StreamEventKind.FINISH,
                        finish_reason=_STOP_REASONS.get(stop, FinishReason.STOP),
                    ),
                )
            return ()

        return ()

    def observe_error(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return the neutral reading of a Messages error document."""
        error = document.get("error")
        error = error if isinstance(error, Mapping) else document
        return ErrorObservation(
            status_code=status_code,
            error_code=str(error.get("type") or "") or None,
            message=str(error.get("message") or ""),
            body=dict(document),
        )


__all__ = ["AnthropicAdapter"]
