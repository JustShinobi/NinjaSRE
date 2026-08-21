"""AWS Bedrock, through the Converse API.

Converse is the one Bedrock surface with a single request shape across model
families, which is what makes one adapter possible at all. Three things are
specific to it:

- **Model identifiers are prefixed and regional.** An inference profile
  identifier is region-scoped and is what actually routes; the descriptor's
  ``deployment_id`` carries it when an operator has one.
- **There is no native JSON mode.** Structured output goes through tool
  coercion, which the client selects from the descriptor's flag rather than
  discovering by getting a rejection.
- **Cache markers are content blocks** (`cachePoint`) rather than keywords on
  another block.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.llm import PROVIDER_AWS_BEDROCK
from core.llm.cache import CachePlan
from core.llm.credentials import ProviderCredentials
from core.llm.failures import ErrorObservation
from core.llm.providers.base import BaseAdapter, ParsedResponse
from core.llm.registry import ModelDescriptor
from core.llm.structured.native import WireFamily
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
    "content_filtered": FinishReason.CONTENT_FILTER,
    "guardrail_intervened": FinishReason.CONTENT_FILTER,
}

_CACHE_POINT = {"cachePoint": {"type": "default"}}


def _content_blocks(message: Message) -> list[dict[str, Any]]:
    """Return one message's content in Converse's block shape."""
    blocks: list[dict[str, Any]] = []

    for result in message.tool_results:
        blocks.append(
            {
                "toolResult": {
                    "toolUseId": result.call_id,
                    "content": [{"text": result.content}],
                    "status": "error" if result.is_error else "success",
                }
            }
        )

    if message.text:
        blocks.append({"text": message.text})

    for call in message.tool_calls:
        blocks.append(
            {
                "toolUse": {
                    "toolUseId": call.id,
                    "name": call.name,
                    "input": dict(call.arguments),
                }
            }
        )

    return blocks


def _parse_usage(document: Mapping[str, Any]) -> TokenCounts:
    """Return the token counts from a Converse ``usage`` block."""
    usage = document.get("usage")
    if not isinstance(usage, Mapping):
        return TokenCounts(estimated=True)

    return TokenCounts(
        input_tokens=int(usage.get("inputTokens") or 0),
        output_tokens=int(usage.get("outputTokens") or 0),
        cached_input_tokens=int(usage.get("cacheReadInputTokens") or 0),
        cache_write_tokens=int(usage.get("cacheWriteInputTokens") or 0),
    )


class BedrockAdapter(BaseAdapter):
    """Translates the neutral vocabulary to and from the Converse API."""

    provider_identifier = PROVIDER_AWS_BEDROCK
    wire = WireFamily.NONE

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the Converse body for ``request``."""
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                continue
            role = "assistant" if message.role is Role.ASSISTANT else "user"
            blocks = _content_blocks(message)
            if blocks:
                messages.append({"role": role, "content": blocks})

        payload: dict[str, Any] = {
            "modelId": descriptor.wire_model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": request.max_output_tokens or descriptor.max_output_tokens,
            },
        }

        if request.system:
            system: list[dict[str, Any]] = [{"text": request.system}]
            if cache.enabled and cache.mark_system:
                system.append(dict(_CACHE_POINT))
            payload["system"] = system

        if request.tools:
            tools: list[dict[str, Any]] = [
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {"json": dict(tool.parameters)},
                    }
                }
                for tool in request.tools
            ]
            if cache.enabled and cache.mark_system:
                tools.append(dict(_CACHE_POINT))
            tool_config: dict[str, Any] = {"tools": tools}
            if request.force_tool_call:
                # Obliges the model to call one of the declared tools — the
                # preflight probe's own way of finding out whether tool calling
                # actually works, rather than whether the model is willing to.
                tool_config["toolChoice"] = {"any": {}}
            payload["toolConfig"] = tool_config

        if request.stop_sequences:
            payload["inferenceConfig"]["stopSequences"] = list(request.stop_sequences)

        if request.reasoning_effort is not None and descriptor.supports_reasoning_effort:
            payload["additionalModelRequestFields"] = {
                "output_config": {"effort": request.reasoning_effort.value}
            }

        return payload

    def parse_response(
        self, document: Mapping[str, Any], descriptor: ModelDescriptor
    ) -> ParsedResponse:
        """Return the Converse document read into neutral terms."""
        output = document.get("output")
        message = output.get("message") if isinstance(output, Mapping) else None
        blocks = message.get("content") if isinstance(message, Mapping) else None
        blocks = blocks if isinstance(blocks, Sequence) and not isinstance(blocks, str) else []

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            if "text" in block and isinstance(block["text"], str):
                text_parts.append(block["text"])
            use = block.get("toolUse")
            if isinstance(use, Mapping):
                arguments = use.get("input")
                tool_calls.append(
                    ToolCall(
                        id=str(use.get("toolUseId") or ""),
                        name=str(use.get("name") or ""),
                        arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
                    )
                )

        raw_stop = str(document.get("stopReason") or "end_turn")
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
        """Return the events one Converse stream event carries."""
        delta_block = chunk.get("contentBlockDelta")
        if isinstance(delta_block, Mapping):
            delta = delta_block.get("delta")
            if isinstance(delta, Mapping):
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return (StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=text),)
            return ()

        start = chunk.get("contentBlockStart")
        if isinstance(start, Mapping):
            begin = start.get("start")
            use = begin.get("toolUse") if isinstance(begin, Mapping) else None
            if isinstance(use, Mapping):
                return (
                    StreamEvent(
                        kind=StreamEventKind.TOOL_CALL,
                        tool_call=ToolCall(
                            id=str(use.get("toolUseId") or ""),
                            name=str(use.get("name") or ""),
                        ),
                    ),
                )
            return ()

        stop = chunk.get("messageStop")
        if isinstance(stop, Mapping):
            raw = str(stop.get("stopReason") or "end_turn")
            return (
                StreamEvent(
                    kind=StreamEventKind.FINISH,
                    finish_reason=_STOP_REASONS.get(raw, FinishReason.STOP),
                ),
            )

        if isinstance(chunk.get("metadata"), Mapping):
            return (StreamEvent(kind=StreamEventKind.USAGE),)

        return ()

    def observe_error(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return the neutral reading of a Bedrock error document.

        botocore reports the code under ``Error.Code`` and the status under
        ``ResponseMetadata``, so a caught exception and a returned document read
        the same way.
        """
        error = document.get("Error")
        error = error if isinstance(error, Mapping) else document
        metadata = document.get("ResponseMetadata")
        status = status_code
        if status is None and isinstance(metadata, Mapping):
            candidate = metadata.get("HTTPStatusCode")
            status = candidate if isinstance(candidate, int) else None

        return ErrorObservation(
            status_code=status,
            error_code=str(error.get("Code") or error.get("code") or "") or None,
            message=str(error.get("Message") or error.get("message") or ""),
            body=dict(document),
        )

    def routing(
        self, credentials: ProviderCredentials, descriptor: ModelDescriptor
    ) -> Mapping[str, str]:
        """Return the region, which selects both the endpoint and the model's availability."""
        region = credentials.get("region")
        return {"region": region} if region else {}


__all__ = ["BedrockAdapter"]
