"""Recorded provider responses, one set per wire family.

These are the shapes the vendors actually return, written down. Recording them
is what lets the contract suite assert parity across all nine providers on every
pull request without a credential, a network, or a token.

A cassette is a plain document because that is exactly what an adapter parses:
the SDK transport turns a vendor response object into one before the parse path
sees it, so a replayed document and a live call are the same input.

Four families cover nine providers, which is the same reason there are only four
payload builders in ``core/llm/providers/``.
"""

from __future__ import annotations

from typing import Any

from config.constants.llm import (
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)

ANTHROPIC_WIRE = "anthropic"
OPENAI_WIRE = "openai"
BEDROCK_WIRE = "bedrock"
GOOGLE_WIRE = "google"

WIRE_BY_PROVIDER: dict[str, str] = {
    PROVIDER_ANTHROPIC: ANTHROPIC_WIRE,
    PROVIDER_OPENAI: OPENAI_WIRE,
    PROVIDER_AZURE_OPENAI: OPENAI_WIRE,
    PROVIDER_OPENROUTER: OPENAI_WIRE,
    PROVIDER_NVIDIA_NIM: OPENAI_WIRE,
    PROVIDER_OLLAMA: OPENAI_WIRE,
    PROVIDER_AWS_BEDROCK: BEDROCK_WIRE,
    PROVIDER_GOOGLE_GEMINI: GOOGLE_WIRE,
    PROVIDER_GOOGLE_VERTEX_AI: GOOGLE_WIRE,
}

#: What every cassette's happy path claims, so one assertion covers all nine.
EXPECTED_TEXT = "The checkout service is returning 503 from two of six pods."
EXPECTED_TOOL_NAME = "kubernetes_list_pods"
EXPECTED_TOOL_ARGUMENTS = {"namespace": "checkout"}
EXPECTED_INPUT_TOKENS = 1_200
EXPECTED_OUTPUT_TOKENS = 340
EXPECTED_CACHED_TOKENS = 800

#: The structured answer every provider is expected to produce, whichever
#: mechanism it had to use to get there.
EXPECTED_STRUCTURED = {"root_cause": "connection pool exhaustion", "confidence": 0.82}


def _anthropic_text() -> dict[str, Any]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": EXPECTED_TEXT}],
        "stop_reason": "end_turn",
        "usage": {
            # This wire reports the uncached remainder, so no arithmetic is
            # needed to reach the neutral shape.
            "input_tokens": EXPECTED_INPUT_TOKENS - EXPECTED_CACHED_TOKENS,
            "output_tokens": EXPECTED_OUTPUT_TOKENS,
            "cache_read_input_tokens": EXPECTED_CACHED_TOKENS,
            "cache_creation_input_tokens": 0,
        },
    }


def _anthropic_tool_call() -> dict[str, Any]:
    document = _anthropic_text()
    document["content"] = [
        {"type": "text", "text": "Checking the pods."},
        {
            "type": "tool_use",
            "id": "toolu_01",
            "name": EXPECTED_TOOL_NAME,
            "input": dict(EXPECTED_TOOL_ARGUMENTS),
        },
    ]
    document["stop_reason"] = "tool_use"
    return document


def _openai_text() -> dict[str, Any]:
    return {
        "id": "chatcmpl-01",
        "object": "chat.completion",
        "model": "gpt-4.1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": EXPECTED_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            # This wire's prompt count *includes* the cached tokens, which is
            # why the adapter subtracts and this cassette does not.
            "prompt_tokens": EXPECTED_INPUT_TOKENS,
            "completion_tokens": EXPECTED_OUTPUT_TOKENS,
            "total_tokens": EXPECTED_INPUT_TOKENS + EXPECTED_OUTPUT_TOKENS,
            "prompt_tokens_details": {"cached_tokens": EXPECTED_CACHED_TOKENS},
        },
    }


def _openai_tool_call() -> dict[str, Any]:
    document = _openai_text()
    document["choices"] = [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_01",
                        "type": "function",
                        # Arguments arrive as a JSON *string* on this wire.
                        "function": {
                            "name": EXPECTED_TOOL_NAME,
                            "arguments": '{"namespace": "checkout"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ]
    return document


def _bedrock_text() -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": EXPECTED_TEXT}]}},
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": EXPECTED_INPUT_TOKENS - EXPECTED_CACHED_TOKENS,
            "outputTokens": EXPECTED_OUTPUT_TOKENS,
            "totalTokens": EXPECTED_INPUT_TOKENS + EXPECTED_OUTPUT_TOKENS,
            "cacheReadInputTokens": EXPECTED_CACHED_TOKENS,
            "cacheWriteInputTokens": 0,
        },
        "ResponseMetadata": {"HTTPStatusCode": 200},
    }


def _bedrock_tool_call() -> dict[str, Any]:
    document = _bedrock_text()
    document["output"] = {
        "message": {
            "role": "assistant",
            "content": [
                {"text": "Checking the pods."},
                {
                    "toolUse": {
                        "toolUseId": "tooluse_01",
                        "name": EXPECTED_TOOL_NAME,
                        "input": dict(EXPECTED_TOOL_ARGUMENTS),
                    }
                },
            ],
        }
    }
    document["stopReason"] = "tool_use"
    return document


def _google_text() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": EXPECTED_TEXT}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": EXPECTED_INPUT_TOKENS,
            "candidatesTokenCount": EXPECTED_OUTPUT_TOKENS,
            "cachedContentTokenCount": EXPECTED_CACHED_TOKENS,
            "totalTokenCount": EXPECTED_INPUT_TOKENS + EXPECTED_OUTPUT_TOKENS,
        },
    }


def _google_tool_call() -> dict[str, Any]:
    document = _google_text()
    document["candidates"] = [
        {
            "content": {
                "role": "model",
                "parts": [
                    {"text": "Checking the pods."},
                    {
                        # No call identifier on this wire; the adapter has to
                        # synthesise one, and the contract suite checks it does.
                        "functionCall": {
                            "name": EXPECTED_TOOL_NAME,
                            "args": dict(EXPECTED_TOOL_ARGUMENTS),
                        }
                    },
                ],
            },
            "finishReason": "STOP",
        }
    ]
    return document


_TEXT_BUILDERS = {
    ANTHROPIC_WIRE: _anthropic_text,
    OPENAI_WIRE: _openai_text,
    BEDROCK_WIRE: _bedrock_text,
    GOOGLE_WIRE: _google_text,
}

_TOOL_CALL_BUILDERS = {
    ANTHROPIC_WIRE: _anthropic_tool_call,
    OPENAI_WIRE: _openai_tool_call,
    BEDROCK_WIRE: _bedrock_tool_call,
    GOOGLE_WIRE: _google_tool_call,
}


def text_response(provider_id: str) -> dict[str, Any]:
    """Return a plain text reply in ``provider_id``'s wire shape."""
    return _TEXT_BUILDERS[WIRE_BY_PROVIDER[provider_id]]()


def tool_call_response(provider_id: str) -> dict[str, Any]:
    """Return a reply carrying one tool call, in ``provider_id``'s wire shape."""
    return _TOOL_CALL_BUILDERS[WIRE_BY_PROVIDER[provider_id]]()


def structured_response(provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a reply whose text is ``payload`` as JSON.

    Native structured output constrains the *text* to the schema — the JSON
    arrives as content, not as a separate field — so this is the same document
    the happy path produces with different text in it.
    """
    import json

    body = json.dumps(payload)
    wire = WIRE_BY_PROVIDER[provider_id]

    if wire == ANTHROPIC_WIRE:
        document = _anthropic_text()
        document["content"] = [{"type": "text", "text": body}]
        return document
    if wire == OPENAI_WIRE:
        document = _openai_text()
        document["choices"][0]["message"]["content"] = body
        return document
    if wire == BEDROCK_WIRE:
        document = _bedrock_text()
        document["output"]["message"]["content"] = [{"text": body}]
        return document
    document = _google_text()
    document["candidates"][0]["content"]["parts"] = [{"text": body}]
    return document


def coerced_structured_response(provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a reply that answers by calling the structured-output tool."""
    from core.llm.structured.tool_coercion import STRUCTURED_OUTPUT_TOOL_NAME

    wire = WIRE_BY_PROVIDER[provider_id]

    if wire == ANTHROPIC_WIRE:
        document = _anthropic_text()
        document["content"] = [
            {
                "type": "tool_use",
                "id": "toolu_structured",
                "name": STRUCTURED_OUTPUT_TOOL_NAME,
                "input": dict(payload),
            }
        ]
        document["stop_reason"] = "tool_use"
        return document

    if wire == OPENAI_WIRE:
        import json

        document = _openai_text()
        document["choices"][0]["message"] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_structured",
                    "type": "function",
                    "function": {
                        "name": STRUCTURED_OUTPUT_TOOL_NAME,
                        "arguments": json.dumps(payload),
                    },
                }
            ],
        }
        document["choices"][0]["finish_reason"] = "tool_calls"
        return document

    if wire == BEDROCK_WIRE:
        document = _bedrock_text()
        document["output"]["message"]["content"] = [
            {
                "toolUse": {
                    "toolUseId": "tooluse_structured",
                    "name": STRUCTURED_OUTPUT_TOOL_NAME,
                    "input": dict(payload),
                }
            }
        ]
        document["stopReason"] = "tool_use"
        return document

    document = _google_text()
    document["candidates"][0]["content"]["parts"] = [
        {"functionCall": {"name": STRUCTURED_OUTPUT_TOOL_NAME, "args": dict(payload)}}
    ]
    return document


def prose_structured_response(provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the mess a quantised local model actually produces.

    JSON inside a fenced block, with a sentence in front of it and a trailing
    comma. Every element here has been observed; none is invented to make the
    parser look good.
    """
    import json

    body = json.dumps(payload, indent=2)
    with_trailing_comma = body.replace("\n}", ",\n}")
    text = f"Here is the analysis you asked for:\n\n```json\n{with_trailing_comma}\n```\n"

    wire = WIRE_BY_PROVIDER[provider_id]
    if wire == ANTHROPIC_WIRE:
        document = _anthropic_text()
        document["content"] = [{"type": "text", "text": text}]
        return document
    if wire == OPENAI_WIRE:
        document = _openai_text()
        document["choices"][0]["message"]["content"] = text
        return document
    if wire == BEDROCK_WIRE:
        document = _bedrock_text()
        document["output"]["message"]["content"] = [{"text": text}]
        return document
    document = _google_text()
    document["candidates"][0]["content"]["parts"] = [{"text": text}]
    return document


def stream_chunks(provider_id: str) -> tuple[dict[str, Any], ...]:
    """Return a streamed generation in ``provider_id``'s wire shape."""
    wire = WIRE_BY_PROVIDER[provider_id]

    if wire == ANTHROPIC_WIRE:
        return (
            {"type": "message_start", "message": {"id": "msg_01"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "The checkout "},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "service is failing."},
            },
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"},
        )

    if wire == OPENAI_WIRE:
        return (
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]},
            {"choices": [{"index": 0, "delta": {"content": "The checkout "}}]},
            {"choices": [{"index": 0, "delta": {"content": "service is failing."}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        )

    if wire == BEDROCK_WIRE:
        return (
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "The checkout "}, "contentBlockIndex": 0}},
            {
                "contentBlockDelta": {
                    "delta": {"text": "service is failing."},
                    "contentBlockIndex": 0,
                }
            },
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5}}},
        )

    return (
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "The checkout "}]}}]},
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "service is failing."}]}}
            ]
        },
        {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "STOP"}]},
    )


def error_document(provider_id: str, *, code: str, message: str) -> dict[str, Any]:
    """Return an error in ``provider_id``'s wire shape."""
    wire = WIRE_BY_PROVIDER[provider_id]

    if wire == ANTHROPIC_WIRE:
        return {"type": "error", "error": {"type": code, "message": message}}
    if wire == OPENAI_WIRE:
        return {"error": {"code": code, "type": code, "message": message}}
    if wire == BEDROCK_WIRE:
        return {"Error": {"Code": code, "Message": message}}
    return {"error": {"status": code, "message": message, "code": 400}}


__all__ = [
    "EXPECTED_CACHED_TOKENS",
    "EXPECTED_INPUT_TOKENS",
    "EXPECTED_OUTPUT_TOKENS",
    "EXPECTED_STRUCTURED",
    "EXPECTED_TEXT",
    "EXPECTED_TOOL_ARGUMENTS",
    "EXPECTED_TOOL_NAME",
    "WIRE_BY_PROVIDER",
    "coerced_structured_response",
    "error_document",
    "prose_structured_response",
    "stream_chunks",
    "structured_response",
    "text_response",
    "tool_call_response",
]
