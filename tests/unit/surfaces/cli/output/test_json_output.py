"""The envelope every ``--json`` document is wrapped in.

Every command's ``--json`` has to validate against a published schema. That is
asserted end to end in ``tests/contract/cli``; this is the mechanism
underneath it — the envelope, the identifier, and the validator's ability to
say *which* field diverged rather than only that something did.
"""

from __future__ import annotations

import json

import pytest

from config.constants.surfaces import (
    JSON_ENVELOPE_KEYS,
    JSON_SCHEMA_PREFIX,
    JSON_SCHEMA_VERSION,
)
from surfaces.cli.output.json_ import Envelope, envelope_of, failure, render
from surfaces.cli.output.schemas import (
    COMMAND_SCHEMAS,
    ENVELOPE_SCHEMA,
    problems,
    published,
    schema_id,
    validate,
)

pytestmark = pytest.mark.unit


def _memory_stats() -> dict[str, object]:
    """Return a payload that satisfies the ``memory.stats`` schema."""
    return {
        "episodes": 3,
        "components": 2,
        "mean_effectiveness": 0.5,
        "oldest_at": "",
        "newest_at": "",
        "read_enabled": True,
        "write_enabled": True,
    }


def test_the_envelope_carries_exactly_the_documented_keys() -> None:
    record = envelope_of("memory.stats", _memory_stats()).to_record()

    assert tuple(sorted(record)) == tuple(sorted(JSON_ENVELOPE_KEYS))


def test_the_schema_identifier_carries_the_version() -> None:
    identifier = schema_id("runs.list")

    assert identifier == f"{JSON_SCHEMA_PREFIX}.runs.list.{JSON_SCHEMA_VERSION}"


def test_a_space_in_a_command_name_becomes_a_dot() -> None:
    assert schema_id("runs list") == schema_id("runs.list")


def test_rendering_produces_parseable_json() -> None:
    document = json.loads(render(envelope_of("memory.stats", _memory_stats())))

    assert document["ok"] is True
    assert document["data"]["episodes"] == 3
    assert document["errors"] == []


def test_a_payload_missing_a_documented_field_is_refused() -> None:
    incomplete = _memory_stats()
    del incomplete["episodes"]

    with pytest.raises(ValueError, match=r"\$\.episodes: required and missing"):
        render(Envelope(command="memory.stats", data=incomplete))


def test_a_payload_with_an_undocumented_field_is_refused() -> None:
    # The drift the schemas exist to catch: a field added to the payload and
    # not to the published document.
    extended = {**_memory_stats(), "surprise": 1}

    with pytest.raises(ValueError, match=r"\$\.surprise: not in the published schema"):
        render(Envelope(command="memory.stats", data=extended))


def test_a_field_of_the_wrong_type_is_refused_and_names_the_field() -> None:
    wrong = {**_memory_stats(), "episodes": "three"}

    with pytest.raises(ValueError, match=r"\$\.episodes: expected integer, got str"):
        render(Envelope(command="memory.stats", data=wrong))


def test_a_bool_is_not_accepted_where_a_number_is_documented() -> None:
    # Python says a bool is an int. JSON does not, and a reader adding token
    # counts would silently get 1.
    wrong = {**_memory_stats(), "episodes": True}

    assert problems(wrong, COMMAND_SCHEMAS["memory.stats"])


def test_a_failure_envelope_validates_without_a_payload() -> None:
    document = json.loads(render(failure("runs.show", "no run named 'nope'")))

    assert document["ok"] is False
    assert document["data"] == {}
    assert document["errors"] == ["no run named 'nope'"]


def test_a_warning_rides_with_a_successful_envelope() -> None:
    envelope = envelope_of("memory.stats", _memory_stats(), warnings=("corpus is empty",))

    assert envelope.ok
    assert envelope.errors == ("corpus is empty",)


def test_every_published_schema_is_a_self_describing_document() -> None:
    for command in COMMAND_SCHEMAS:
        document = published(command)
        assert document["$id"] == schema_id(command)
        assert document["properties"]["data"] == dict(COMMAND_SCHEMAS[command])


def test_nested_divergence_is_located_by_path() -> None:
    found = problems(
        {"runs": [{"run_id": 1}], "cost": {}},
        COMMAND_SCHEMAS["runs.list"],
    )

    assert any(problem.startswith("$.runs[0].run_id") for problem in found)


def test_the_envelope_schema_requires_every_documented_key() -> None:
    assert set(ENVELOPE_SCHEMA["required"]) == set(JSON_ENVELOPE_KEYS)


def test_validate_passes_a_conforming_document() -> None:
    validate(envelope_of("memory.stats", _memory_stats()).to_record(), ENVELOPE_SCHEMA)
