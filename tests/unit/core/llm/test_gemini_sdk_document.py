"""The Gemini adapter must read the document the SDK transport actually hands it.

Two paths reach ``parse_response`` and they disagree about spelling. A direct
HTTP call returns the REST wire format, in camelCase. The SDK transport — the
one every deployment runs, because ``google.genai`` is what
``core/llm/transports/sdk.py`` sends through — serialises the response with
``model_dump()``, and pydantic's default is the field name, which is snake_case.

The adapter read camelCase only, so on the path that runs:

- **every tool call vanished.** ``functionCall`` is not in the document;
  ``function_call`` is. The model called the tool, the platform saw text, and
  the provider verification recorded "the model answered without calling the
  tool, even though the call was mandatory" against a model that had done
  exactly as it was told. Every investigation is a sequence of tool calls, so
  the platform could not run one through Gemini at all.
- **the finish reason was always ``STOP``**, because ``finishReason`` is
  ``finish_reason`` there — so a response truncated at the token limit was
  indistinguishable from a complete one.

``_parse_usage`` already reads both spellings; somebody found this defect in the
token counts and fixed it there. These are the other two places it lives.

The documents below were captured from ``google-genai`` 2.19.0 in the running
deployment. ``test_the_fixture_is_the_shape_the_sdk_really_produces`` re-derives
them from the SDK when the extra is installed, so the fixture cannot rot into a
shape nothing produces.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.llm.providers.gemini import GeminiAdapter
from core.llm.registry import ModelDescriptor
from core.llm.types import FinishReason, StreamEventKind

pytestmark = pytest.mark.unit


def _descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        model_id="gemini-flash-latest",
        provider_id="google_gemini",
        context_window=1_000_000,
        max_output_tokens=8_192,
    )


#: One response carrying a tool call, as ``GenerateContentResponse.model_dump()``
#: renders it: snake_case throughout, and every unset field present as ``None``.
SDK_TOOL_CALL: dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [
                    {"text": None, "function_call": {"name": "echo", "args": {"token": "ok"}}}
                ],
            },
            "finish_reason": "STOP",
        }
    ],
    "usage_metadata": {"prompt_token_count": 11, "candidates_token_count": 5},
}

#: The same answer as the REST wire renders it. Both must parse identically.
REST_TOOL_CALL: dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"functionCall": {"name": "echo", "args": {"token": "ok"}}}],
            },
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5},
}


@pytest.mark.parametrize(
    ("document", "spelling"),
    [(SDK_TOOL_CALL, "snake_case"), (REST_TOOL_CALL, "camelCase")],
)
def test_a_tool_call_is_read_in_either_spelling(document: dict[str, Any], spelling: str) -> None:
    parsed = GeminiAdapter().parse_response(document, _descriptor())

    assert [call.name for call in parsed.tool_calls] == ["echo"], spelling
    assert parsed.tool_calls[0].arguments == {"token": "ok"}
    # A call was made, so the turn ended to make one — not because the model
    # had finished speaking. The loop reads this to decide whether to continue.
    assert parsed.finish_reason is FinishReason.TOOL_CALLS


def test_a_truncated_answer_is_not_reported_as_a_complete_one() -> None:
    document = {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": "as I was say"}]},
                "finish_reason": "MAX_TOKENS",
            }
        ],
        "usage_metadata": {"prompt_token_count": 3, "candidates_token_count": 64},
    }

    parsed = GeminiAdapter().parse_response(document, _descriptor())

    assert parsed.finish_reason is FinishReason.LENGTH


def test_a_streamed_tool_call_is_read_in_the_sdk_spelling() -> None:
    """The stream goes through the same senders and the same serialiser, so it
    carries the same spelling — and a streamed tool call that vanished would
    vanish the same way."""
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [{"function_call": {"name": "echo", "args": {"token": "ok"}}}]
                },
                "finish_reason": "STOP",
            }
        ]
    }

    events = GeminiAdapter().parse_stream_chunk(chunk)

    kinds = [event.kind for event in events]
    assert StreamEventKind.TOOL_CALL in kinds
    assert next(e for e in events if e.kind is StreamEventKind.TOOL_CALL).tool_call is not None


def test_text_is_unaffected_because_that_field_is_spelled_the_same() -> None:
    """Which is why authentication passed and tool calling did not: the probe
    that only needs text worked, so nothing upstream looked wrong."""
    document = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "ready"}]}}],
        "usage_metadata": {"prompt_token_count": 3, "candidates_token_count": 1},
    }

    parsed = GeminiAdapter().parse_response(document, _descriptor())

    assert parsed.text == "ready"


def test_the_fixture_is_the_shape_the_sdk_really_produces() -> None:
    """Skipped where the ``google`` extra is not installed, which is the ordinary
    development environment — and run in CI and anywhere the provider is."""
    types = pytest.importorskip("google.genai").types

    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(name="echo", args={"token": "ok"})
                        )
                    ],
                ),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=11, candidates_token_count=5
        ),
    )
    document = response.model_dump()

    candidate = document["candidates"][0]
    assert "finish_reason" in candidate
    assert "function_call" in candidate["content"]["parts"][0]
    assert "usage_metadata" in document

    parsed = GeminiAdapter().parse_response(document, _descriptor())
    assert [call.name for call in parsed.tool_calls] == ["echo"]
