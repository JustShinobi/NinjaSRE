"""Google Gemini, and Vertex AI serving the same wire.

The `generateContent` shape differs from both other wires in ways that are easy
to get subtly wrong:

- The assistant role is called ``model``.
- A system prompt is ``systemInstruction``, a content object rather than a
  string.
- Tool results are ``functionResponse`` parts inside a *user* turn, and carry
  the tool's **name** rather than a call identifier — so a neutral call id has
  to be reconstructed on the way back, and matched by name on the way out.
- Everything that is not content lives under ``config``.

Vertex is the same wire with different authentication and a different model
namespace, so it is a subclass and not a copy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.llm import PROVIDER_GOOGLE_GEMINI, PROVIDER_GOOGLE_VERTEX_AI
from core.llm.cache import CachePlan
from core.llm.credentials import ProviderCredentials
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

_FINISH_REASONS: dict[str, FinishReason] = {
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.CONTENT_FILTER,
    "RECITATION": FinishReason.CONTENT_FILTER,
    "BLOCKLIST": FinishReason.CONTENT_FILTER,
    "PROHIBITED_CONTENT": FinishReason.CONTENT_FILTER,
    "SPII": FinishReason.CONTENT_FILTER,
    "MALFORMED_FUNCTION_CALL": FinishReason.ERROR,
}


def _parts(message: Message) -> list[dict[str, Any]]:
    """Return one message's content as `generateContent` parts."""
    parts: list[dict[str, Any]] = []

    for result in message.tool_results:
        parts.append(
            {
                "functionResponse": {
                    "name": result.name,
                    "response": {"result": result.content, "is_error": result.is_error},
                }
            }
        )

    if message.text:
        parts.append({"text": message.text})

    for call in message.tool_calls:
        parts.append({"functionCall": {"name": call.name, "args": dict(call.arguments)}})

    return parts


def _parse_usage(document: Mapping[str, Any]) -> TokenCounts:
    """Return the token counts from a ``usageMetadata`` block.

    ``promptTokenCount`` includes the cached tokens, as on the OpenAI wire, so
    the cached count is subtracted to keep the neutral fields disjoint.
    """
    usage = document.get("usageMetadata")
    if not isinstance(usage, Mapping):
        return TokenCounts(estimated=True)

    prompt = int(usage.get("promptTokenCount") or 0)
    cached = int(usage.get("cachedContentTokenCount") or 0)

    return TokenCounts(
        input_tokens=max(prompt - cached, 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
        cached_input_tokens=cached,
        reasoning_tokens=int(usage.get("thoughtsTokenCount") or 0),
    )


def _read_parts(parts: Any) -> tuple[str, tuple[ToolCall, ...]]:
    """Return the text and tool calls a part list carries."""
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    if not isinstance(parts, Sequence) or isinstance(parts, str):
        return "", ()

    for index, part in enumerate(parts):
        if not isinstance(part, Mapping):
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            text_parts.append(text)
        function_call = part.get("functionCall")
        if isinstance(function_call, Mapping):
            arguments = function_call.get("args")
            name = str(function_call.get("name") or "")
            calls.append(
                ToolCall(
                    # This wire sends no call identifier. One is synthesised
                    # from the name and position so the runtime can pair a
                    # result back, and so a trace can tell two calls apart.
                    id=str(function_call.get("id") or f"{name}_{index}"),
                    name=name,
                    arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
                )
            )

    return "".join(text_parts), tuple(calls)


class GeminiAdapter(BaseAdapter):
    """Translates the neutral vocabulary to and from `generateContent`."""

    provider_identifier = PROVIDER_GOOGLE_GEMINI
    wire = WireFamily.GOOGLE

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the `generateContent` body for ``request``."""
        contents: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                continue
            role = "model" if message.role is Role.ASSISTANT else "user"
            parts = _parts(message)
            if parts:
                contents.append({"role": role, "parts": parts})

        config: dict[str, Any] = {
            "maxOutputTokens": request.max_output_tokens or descriptor.max_output_tokens,
        }

        if request.system:
            config["systemInstruction"] = {"parts": [{"text": request.system}]}

        if request.tools:
            config["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": dict(tool.parameters),
                        }
                        for tool in request.tools
                    ]
                }
            ]
            if not request.parallel_tool_calls or not descriptor.supports_parallel_tool_calls:
                config["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        if request.stop_sequences:
            config["stopSequences"] = list(request.stop_sequences)

        if request.response_schema is not None and descriptor.supports_structured_output:
            fields = native_request_fields(request.response_schema, self.dialect, self.wire_family)
            config.update(fields.get("generationConfig", {}))

        return {"model": descriptor.wire_model_id, "contents": contents, "config": config}

    def parse_response(
        self, document: Mapping[str, Any], descriptor: ModelDescriptor
    ) -> ParsedResponse:
        """Return the `generateContent` document read into neutral terms."""
        candidates = document.get("candidates")
        if not isinstance(candidates, Sequence) or not candidates:
            return ParsedResponse(
                finish_reason=FinishReason.ERROR,
                tokens=_parse_usage(document),
                degradations=(
                    Degradation(DegradationKind.USAGE_ESTIMATED, "response carried no candidates"),
                ),
            )

        candidate = candidates[0]
        candidate = candidate if isinstance(candidate, Mapping) else {}
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, Mapping) else None
        text, tool_calls = _read_parts(parts)

        raw_finish = str(candidate.get("finishReason") or "STOP").upper()
        finish_reason = _FINISH_REASONS.get(raw_finish, FinishReason.STOP)
        if tool_calls and finish_reason is FinishReason.STOP:
            finish_reason = FinishReason.TOOL_CALLS

        tokens = _parse_usage(document)
        degradations: tuple[Degradation, ...] = ()
        if tokens.estimated:
            degradations = (
                Degradation(DegradationKind.USAGE_ESTIMATED, "provider omitted usageMetadata"),
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
        candidates = chunk.get("candidates")
        if not isinstance(candidates, Sequence) or not candidates:
            return ()

        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            return ()

        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, Mapping) else None
        text, tool_calls = _read_parts(parts)

        events: list[StreamEvent] = []
        if text:
            events.append(StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=text))
        for call in tool_calls:
            events.append(StreamEvent(kind=StreamEventKind.TOOL_CALL, tool_call=call))

        raw_finish = candidate.get("finishReason")
        if isinstance(raw_finish, str) and raw_finish:
            events.append(
                StreamEvent(
                    kind=StreamEventKind.FINISH,
                    finish_reason=_FINISH_REASONS.get(raw_finish.upper(), FinishReason.STOP),
                )
            )

        return tuple(events)

    def observe_error(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return the neutral reading of a Google error document."""
        error = document.get("error")
        error = error if isinstance(error, Mapping) else document
        status = status_code
        if status is None:
            candidate = error.get("code")
            status = candidate if isinstance(candidate, int) else None

        return ErrorObservation(
            status_code=status,
            error_code=str(error.get("status") or "") or None,
            message=str(error.get("message") or ""),
            body=dict(document),
        )


class VertexAdapter(GeminiAdapter):
    """Vertex AI: the same wire, reached with service-account credentials.

    Vertex serves Claude alongside Gemini under bare first-party identifiers —
    no provider prefix, unlike Bedrock — which the registry rows already carry.
    """

    provider_identifier = PROVIDER_GOOGLE_VERTEX_AI

    def routing(
        self, credentials: ProviderCredentials, descriptor: ModelDescriptor
    ) -> Mapping[str, str]:
        """Return the project and location, which address the endpoint itself."""
        routing: dict[str, str] = {}
        project = credentials.get("project")
        if project:
            routing["project"] = project
        location = credentials.get("location")
        if location:
            routing["location"] = location
        return routing


__all__ = ["GeminiAdapter", "VertexAdapter"]
