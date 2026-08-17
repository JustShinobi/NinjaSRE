"""Forcing a tool call is a property of the request, captured on the wire.

Each adapter translates ``InvokeRequest.force_tool_call`` into its own wire's
way of making a call mandatory. Captured from ``build_payload`` directly —
never through a real call — because the property under test is what goes out
on the wire, and a fixture and a live call are indistinguishable to a pure
function of a document.
"""

from __future__ import annotations

import pytest

from core.llm.cache import CachePlan
from core.llm.providers.anthropic import AnthropicAdapter
from core.llm.providers.bedrock import BedrockAdapter
from core.llm.providers.gemini import GeminiAdapter
from core.llm.providers.openai_compat import OpenAiAdapter
from core.llm.registry import ModelDescriptor
from core.llm.types import InvokeRequest, Message, Role, ToolSchema

pytestmark = pytest.mark.unit

_TOOL = ToolSchema(
    name="echo",
    description="Echo the token back.",
    parameters={"type": "object", "properties": {"token": {"type": "string"}}},
)

_UNCACHED = CachePlan()


def _descriptor(provider_id: str, model_id: str) -> ModelDescriptor:
    return ModelDescriptor(
        model_id=model_id,
        provider_id=provider_id,
        context_window=128_000,
        max_output_tokens=4_096,
    )


def _request(*, force: bool) -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="call the tool"),),
        tools=(_TOOL,),
        max_output_tokens=64,
        force_tool_call=force,
    )


def test_gemini_forces_function_calling_config_mode_any() -> None:
    payload = GeminiAdapter().build_payload(
        _request(force=True), _descriptor("google_gemini", "gemini-2.5-flash"), _UNCACHED
    )

    assert payload["config"]["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"


def test_gemini_without_forcing_carries_no_tool_config_change() -> None:
    """Today's behaviour, unchanged: no forcing means no field appears at all
    for a request whose parallel calls are not being serialised either."""
    payload = GeminiAdapter().build_payload(
        _request(force=False), _descriptor("google_gemini", "gemini-2.5-flash"), _UNCACHED
    )

    assert "toolConfig" not in payload["config"]


def test_anthropic_forces_tool_choice_any() -> None:
    payload = AnthropicAdapter().build_payload(
        _request(force=True), _descriptor("anthropic", "claude-sonnet-5"), _UNCACHED
    )

    assert payload["tool_choice"] == {"type": "any"}


def test_anthropic_without_forcing_carries_no_tool_choice() -> None:
    payload = AnthropicAdapter().build_payload(
        _request(force=False), _descriptor("anthropic", "claude-sonnet-5"), _UNCACHED
    )

    assert "tool_choice" not in payload


def test_openai_wire_forces_tool_choice_required() -> None:
    payload = OpenAiAdapter().build_payload(
        _request(force=True), _descriptor("openai", "gpt-5"), _UNCACHED
    )

    assert payload["tool_choice"] == "required"


def test_openai_wire_without_forcing_carries_no_tool_choice() -> None:
    payload = OpenAiAdapter().build_payload(
        _request(force=False), _descriptor("openai", "gpt-5"), _UNCACHED
    )

    assert "tool_choice" not in payload


def test_bedrock_forces_tool_choice_any() -> None:
    payload = BedrockAdapter().build_payload(
        _request(force=True),
        _descriptor("aws_bedrock", "anthropic.claude-sonnet-5-v1:0"),
        _UNCACHED,
    )

    assert payload["toolConfig"]["toolChoice"] == {"any": {}}


def test_bedrock_without_forcing_carries_no_tool_choice() -> None:
    payload = BedrockAdapter().build_payload(
        _request(force=False),
        _descriptor("aws_bedrock", "anthropic.claude-sonnet-5-v1:0"),
        _UNCACHED,
    )

    assert "toolChoice" not in payload["toolConfig"]
