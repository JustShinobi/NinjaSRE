"""Which declared schemas reach the model, and what happens to the rest.

Two different failures, deliberately kept apart, because the operator's next
action differs. A **malformed** schema is a server breaking the protocol: it is
rejected with an error naming what was wrong, and the operator takes that to
whoever runs the server. An **unnormalisable** schema is well-formed and simply
cannot be expressed as a tool schema on any of the nine providers: it is
excluded with a recorded reason, and neither breaks the catalogue.
"""

from __future__ import annotations

import pytest

from capabilities.protocols.port import MalformedToolSchema
from capabilities.protocols.schema import (
    normalisation_failure,
    normalised_input_schema,
    validate_tool_schema,
)

pytestmark = pytest.mark.unit


# --- malformed: rejected with a specific error (FR-012) ------------------------


def test_a_schema_that_is_not_an_object_is_rejected_naming_what_arrived() -> None:
    with pytest.raises(MalformedToolSchema) as raised:
        validate_tool_schema("a string", server="deploys", tool="rollout")
    assert "deploys.rollout" in str(raised.value)
    assert "str" in str(raised.value)


def test_properties_that_are_not_a_mapping_are_rejected() -> None:
    with pytest.raises(MalformedToolSchema) as raised:
        validate_tool_schema(
            {"type": "object", "properties": ["target"]}, server="deploys", tool="rollout"
        )
    assert "properties" in str(raised.value)


def test_required_that_is_not_a_list_of_names_is_rejected() -> None:
    with pytest.raises(MalformedToolSchema) as raised:
        validate_tool_schema(
            {"type": "object", "properties": {}, "required": "target"},
            server="deploys",
            tool="rollout",
        )
    assert "required" in str(raised.value)

    with pytest.raises(MalformedToolSchema):
        validate_tool_schema(
            {"type": "object", "properties": {}, "required": [1, 2]},
            server="deploys",
            tool="rollout",
        )


def test_a_property_whose_declaration_is_not_an_object_is_rejected() -> None:
    with pytest.raises(MalformedToolSchema) as raised:
        validate_tool_schema(
            {"type": "object", "properties": {"target": "string"}},
            server="deploys",
            tool="rollout",
        )
    assert "target" in str(raised.value)


def test_a_well_formed_schema_passes_and_comes_back_unchanged() -> None:
    schema = {"type": "object", "properties": {"target": {"type": "string"}}, "required": []}
    assert validate_tool_schema(schema, server="deploys", tool="rollout") == schema


def test_a_missing_schema_is_read_as_a_tool_that_takes_nothing() -> None:
    # A server declaring no inputSchema is declaring a no-argument tool. That is
    # not a protocol violation, and treating it as one would exclude a working
    # tool over an omission the specification allows.
    assert validate_tool_schema(None, server="deploys", tool="ping") == {
        "type": "object",
        "properties": {},
    }


# --- unnormalisable: excluded with a reason (FR-004) ---------------------------


def test_a_schema_whose_root_is_not_an_object_cannot_be_a_tool_schema() -> None:
    reason = normalisation_failure({"type": "array", "items": {"type": "string"}})
    assert reason is not None
    assert "object" in reason


def test_a_required_argument_normalisation_would_drop_makes_the_tool_uncallable() -> None:
    # The model would be handed a schema requiring an argument it is never told
    # about, and every call would be rejected as invalid.
    reason = normalisation_failure(
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]}
    )
    assert reason is not None
    assert "b" in reason


def test_an_ordinary_schema_normalises() -> None:
    assert (
        normalisation_failure(
            {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}
        )
        is None
    )


def test_a_schema_using_constructs_a_provider_rejects_still_normalises() -> None:
    # Unions, ``oneOf`` and ``$ref`` are exactly what the normaliser exists for.
    # They must be rewritten, not excluded.
    schema = {
        "type": "object",
        "properties": {
            "target": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
            "mode": {"type": ["string", "null"]},
            "spec": {"$ref": "#/$defs/spec"},
        },
        "required": ["target", "spec"],
        "$defs": {"spec": {"type": "object", "properties": {"name": {"type": "string"}}}},
    }
    assert normalisation_failure(schema) is None

    normalised = normalised_input_schema(schema)
    assert normalised["type"] == "object"
    assert set(normalised["properties"]) >= {"target", "mode", "spec"}
    assert "$defs" not in normalised


def test_the_normalised_schema_is_the_strictest_reading_not_one_providers() -> None:
    # Normalising for the strictest dialect is what makes one stored schema
    # correct on all nine providers rather than on whichever one was configured
    # when the server was registered.
    normalised = normalised_input_schema(
        {"type": "object", "properties": {"n": {"type": ["integer", "null"]}}}
    )
    assert normalised["properties"]["n"].get("type") in {"integer", "string"}
