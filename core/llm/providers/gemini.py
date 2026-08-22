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
        # The signature rides on the part beside the call, which is where it
        # arrived and where this wire looks for it.
        part: dict[str, Any] = {"functionCall": {"name": call.name, "args": dict(call.arguments)}}
        part.update(call.provider_state)
        parts.append(part)

    return parts


def _usage_count(usage: Mapping[str, Any], camel: str, snake: str) -> int:
    """Return one count under whichever spelling the response used.

    ``or 0`` rather than a default, because the SDK sends ``null`` for a count
    it has no value for rather than omitting the key, and ``int(None)`` raises.
    """
    value = usage.get(camel)
    if value is None:
        value = usage.get(snake)
    return int(value or 0)


def _either(document: Mapping[str, Any], wire: str, sdk: str) -> Any:
    """Return whichever spelling of one field this document carries.

    There are two paths to every parser in this module and they disagree. A
    direct HTTP call returns the REST wire format, in camelCase; the SDK
    transport — which is what a deployment actually runs — hands over
    ``model_dump()`` of a pydantic model, and pydantic's default is the field
    name, which is snake_case.

    Reading only the wire spelling is not a cosmetic miss. It made every tool
    call the model made invisible: ``functionCall`` is absent from an SDK
    document, ``function_call`` holds it, and the platform therefore saw a model
    that had answered in prose. Every investigation is a sequence of tool calls,
    so nothing could run. ``_parse_usage`` below already reads both spellings,
    for the same reason found earlier in the token counts.
    """
    found = document.get(wire)
    return document.get(sdk) if found is None else found


def _parse_usage(document: Mapping[str, Any]) -> TokenCounts:
    """Return the token counts from a usage block, in either spelling.

    Two spellings because there are two paths to this parser and they disagree:
    a direct HTTP call returns the REST wire format, in camelCase, and the SDK
    returns the same numbers in snake_case. Reading only the first meant every
    count came back zero on the path a deployment actually runs — and carried a
    degradation saying the provider had omitted what it had in fact sent.

    The prompt count includes the cached tokens, as on the OpenAI wire, so the
    cached count is subtracted to keep the neutral fields disjoint.
    """
    usage = _either(document, "usageMetadata", "usage_metadata")
    if not isinstance(usage, Mapping):
        return TokenCounts(estimated=True)

    prompt = _usage_count(usage, "promptTokenCount", "prompt_token_count")
    cached = _usage_count(usage, "cachedContentTokenCount", "cached_content_token_count")

    return TokenCounts(
        input_tokens=max(prompt - cached, 0),
        output_tokens=_usage_count(usage, "candidatesTokenCount", "candidates_token_count"),
        cached_input_tokens=cached,
        reasoning_tokens=_usage_count(usage, "thoughtsTokenCount", "thoughts_token_count"),
    )


def _signature_of(part: Mapping[str, Any]) -> dict[str, Any]:
    """Return the thought signature this part carried, under the name it used.

    Gemini returns one alongside every ``functionCall`` and refuses the next
    request if the call comes back without it — the whole conversation, not just
    that call. Keyed by the spelling it arrived under so it goes back the way it
    came: the SDK sends ``thought_signature`` and the REST wire
    ``thoughtSignature``, and echoing the other one is the same as echoing none.

    Empty when there is none, so a part that never had one does not gain a null
    field. An absent key and a key set to nothing are different documents.
    """
    for spelling in ("thoughtSignature", "thought_signature"):
        value = part.get(spelling)
        if value:
            return {spelling: value}
    return {}


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
        function_call = _either(part, "functionCall", "function_call")
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
                    provider_state=_signature_of(part),
                )
            )

    return "".join(text_parts), tuple(calls)


def _function_calling_mode(request: InvokeRequest, descriptor: ModelDescriptor) -> str | None:
    """Return the `functionCallingConfig` mode this request needs, or ``None`` for the wire's own default.

    ``"ANY"`` obliges the model to call one of the declared tools — the mode the
    preflight probe turns on to find out whether tool calling actually works,
    rather than merely whether the model is willing to. ``"AUTO"`` is set
    explicitly only to also carry the existing serialised-parallel-calls
    behaviour; an ordinary request that wants neither leaves the field off
    entirely, which is the wire's own default and today's behaviour unchanged.
    """
    if request.force_tool_call:
        return "ANY"
    if not request.parallel_tool_calls or not descriptor.supports_parallel_tool_calls:
        return "AUTO"
    return None


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
            mode = _function_calling_mode(request, descriptor)
            if mode is not None:
                config["toolConfig"] = {"functionCallingConfig": {"mode": mode}}

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

        raw_finish = str(_either(candidate, "finishReason", "finish_reason") or "STOP").upper()
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

        raw_finish = _either(candidate, "finishReason", "finish_reason")
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
