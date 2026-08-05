"""The structured-output ladder, and the mess at the bottom of it.

Every input to the prose parser here is a malformation that local models
actually produce. None is invented to make the parser look good, and the parser
is not asked to guess at meaning: a repair either yields a document that parses
or the next one is tried.
"""

from __future__ import annotations

import json

import pytest

from core.llm.schema import dialect_for
from core.llm.structured.native import WireFamily, native_request_fields
from core.llm.structured.prose_parsing import parse_prose
from core.llm.structured.tool_coercion import (
    STRUCTURED_OUTPUT_TOOL_NAME,
    coercion_tool,
    extract_coerced,
    strip_coercion_calls,
)
from core.llm.types import ToolCall

pytestmark = pytest.mark.unit

_ANSWER = {"root_cause": "connection pool exhaustion", "confidence": 0.82}


# --- Native -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "key"),
    [
        (WireFamily.OPENAI, "response_format"),
        (WireFamily.ANTHROPIC, "output_config"),
        (WireFamily.GOOGLE, "generationConfig"),
    ],
)
def test_each_wire_asks_for_a_schema_in_its_own_way(family: str, key: str) -> None:
    fields = native_request_fields(
        {"type": "object", "properties": {"a": {"type": "string"}}},
        dialect_for("anthropic"),
        family,
    )
    assert key in fields


def test_a_wire_with_no_native_mode_asks_for_nothing() -> None:
    assert native_request_fields({"type": "object"}, dialect_for("ollama"), WireFamily.NONE) == {}


def test_the_structured_schema_goes_through_the_same_dialect_rules() -> None:
    """A provider validates a response schema exactly as strictly as a tool one."""
    fields = native_request_fields(
        {"type": "object", "properties": {"x": {"type": ["string", "null"]}}},
        dialect_for("google_gemini"),
        WireFamily.GOOGLE,
    )

    schema = fields["generationConfig"]["responseSchema"]
    assert schema["properties"]["x"]["type"] == "string"
    assert schema["properties"]["x"]["nullable"] is True


# --- Tool coercion ------------------------------------------------------------


def test_the_coercion_tool_carries_the_schema() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    tool = coercion_tool(schema)

    assert tool.name == STRUCTURED_OUTPUT_TOOL_NAME
    assert tool.parameters == schema


def test_the_first_coercion_call_wins() -> None:
    """Deterministic beats clever: a retry must send and read the same thing."""
    calls = (
        ToolCall(id="1", name=STRUCTURED_OUTPUT_TOOL_NAME, arguments={"pick": "first"}),
        ToolCall(id="2", name=STRUCTURED_OUTPUT_TOOL_NAME, arguments={"pick": "second"}),
    )

    assert extract_coerced(calls) == {"pick": "first"}


def test_no_coercion_call_reads_as_none() -> None:
    assert extract_coerced((ToolCall(id="1", name="something_else"),)) is None


def test_the_scaffolding_is_stripped_from_what_the_caller_sees() -> None:
    calls = (
        ToolCall(id="1", name=STRUCTURED_OUTPUT_TOOL_NAME),
        ToolCall(id="2", name="kubernetes_list_pods"),
    )

    assert [call.name for call in strip_coercion_calls(calls)] == ["kubernetes_list_pods"]


# --- Prose parsing ------------------------------------------------------------


def test_clean_json_parses() -> None:
    assert parse_prose(json.dumps(_ANSWER)) == _ANSWER


def test_json_inside_a_fenced_block_parses() -> None:
    text = f"Here is the analysis:\n\n```json\n{json.dumps(_ANSWER)}\n```\n"
    assert parse_prose(text) == _ANSWER


def test_json_with_prose_in_front_of_it_parses() -> None:
    text = f"After reviewing the logs I concluded the following. {json.dumps(_ANSWER)}"
    assert parse_prose(text) == _ANSWER


def test_a_trailing_comma_is_repaired() -> None:
    text = '{"root_cause": "connection pool exhaustion", "confidence": 0.82,}'
    assert parse_prose(text) == _ANSWER


def test_a_response_cut_off_by_the_token_limit_is_completed() -> None:
    text = '{"root_cause": "connection pool exhaustion", "confidence": 0.82'
    assert parse_prose(text) == _ANSWER


def test_a_truncated_string_is_closed_before_the_brace() -> None:
    parsed = parse_prose('{"root_cause": "connection pool exhaus')
    assert parsed == {"root_cause": "connection pool exhaus"}


def test_a_brace_in_the_prose_does_not_derail_the_scan() -> None:
    text = f"The template {{service}} expanded oddly. Result: {json.dumps(_ANSWER)}"
    assert parse_prose(text) == _ANSWER


def test_a_brace_inside_a_string_does_not_end_the_document() -> None:
    parsed = parse_prose('{"pattern": "a}b", "ok": true}')
    assert parsed == {"pattern": "a}b", "ok": True}


def test_an_escaped_quote_does_not_end_the_string() -> None:
    parsed = parse_prose('{"message": "he said \\"stop\\"", "ok": true}')
    assert parsed == {"message": 'he said "stop"', "ok": True}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "There is no JSON here at all.",
        "[1, 2, 3]",
        '"just a string"',
        "}{",
    ],
)
def test_what_is_not_an_object_reads_as_nothing(text: str) -> None:
    """A bare array is valid JSON and the wrong shape; failing here beats failing later."""
    assert parse_prose(text) is None


def test_an_absurdly_long_response_is_refused_rather_than_scanned() -> None:
    assert parse_prose("x" * 500_000) is None


def test_the_first_object_wins_when_there_are_several() -> None:
    text = f"{json.dumps(_ANSWER)} and then {json.dumps({'other': 1})}"
    assert parse_prose(text) == _ANSWER
