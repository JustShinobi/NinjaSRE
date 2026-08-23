"""Gemini refuses a conversation whose tool calls come back without their signature.

The model returns a `thought_signature` alongside each `functionCall` part, and
requires it echoed back verbatim when that turn is replayed as history. Drop it
and the *second* request of every investigation is refused:

    400 INVALID_ARGUMENT: Function call is missing a thought_signature in
    functionCall parts. This is required for tools to work correctly.

Which is what staging did: the model called a tool, the tool ran, the evidence
was gathered — and the turn after it was rejected, so no investigation could get
past its first tool call.

The neutral vocabulary does not learn what a thought signature is. `ToolCall`
gains somewhere to keep whatever a provider hands back and requires returned,
and this wire is the only thing that knows the name of it.

A hook or a guardrail that rewrites a call's arguments must carry it too. Those
rebuild the call, so they rebuild it with `replace` — a constructor call listing
the fields it knows about is how this silently breaks again the next time a
field is added.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.llm.cache import CachePlan
from core.llm.providers.gemini import GeminiAdapter
from core.llm.registry import ModelDescriptor
from core.llm.types import InvokeRequest, Message, Role, ToolCall

pytestmark = pytest.mark.unit

SIGNATURE = b"opaque-signature-bytes"


def _descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        model_id="gemini-flash-latest",
        provider_id="google_gemini",
        context_window=1_000_000,
        max_output_tokens=8_192,
    )


def test_the_signature_is_read_off_the_part_that_carried_the_call() -> None:
    document = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "function_call": {"name": "prometheus_active_alerts", "args": {}},
                            "thought_signature": SIGNATURE,
                        }
                    ],
                },
                "finish_reason": "STOP",
            }
        ]
    }

    parsed = GeminiAdapter().parse_response(document, _descriptor())

    assert parsed.tool_calls[0].provider_state == {"thought_signature": SIGNATURE}


def test_the_signature_goes_back_on_the_part_it_came_from() -> None:
    call = ToolCall(
        id="prometheus_active_alerts_0",
        name="prometheus_active_alerts",
        provider_state={"thought_signature": SIGNATURE},
    )
    request = InvokeRequest(
        messages=(Message(role=Role.ASSISTANT, tool_calls=(call,)),),
    )

    payload = GeminiAdapter().build_payload(request, _descriptor(), CachePlan())

    part = payload["contents"][0]["parts"][0]
    assert part["functionCall"]["name"] == "prometheus_active_alerts"
    assert part["thought_signature"] == SIGNATURE


def test_a_call_that_carried_no_signature_sends_no_empty_one() -> None:
    """An absent field and a field set to nothing are different documents, and
    only one of them is what a provider that does not use signatures expects."""
    request = InvokeRequest(
        messages=(Message(role=Role.ASSISTANT, tool_calls=(ToolCall(id="a", name="echo"),)),),
    )

    payload = GeminiAdapter().build_payload(request, _descriptor(), CachePlan())

    assert "thought_signature" not in payload["contents"][0]["parts"][0]


def test_rewriting_a_calls_arguments_keeps_everything_else_about_it() -> None:
    """`replace` rather than a constructor: a guardrail that rewrote arguments
    and rebuilt the call by listing fields would drop the signature, and the
    conversation would be refused one turn later for a reason nothing near the
    guardrail mentions."""
    call = ToolCall(id="a", name="echo", provider_state={"thought_signature": SIGNATURE})

    rewritten = replace(call, arguments={"token": "redacted"})

    assert rewritten.provider_state == {"thought_signature": SIGNATURE}
