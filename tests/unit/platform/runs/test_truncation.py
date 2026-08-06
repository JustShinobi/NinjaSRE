"""A payload that did not fit says so, in the payload."""

from __future__ import annotations

from config.constants.runs import (
    MAX_TRACE_PAYLOAD_BYTES,
    MAX_TRACE_PAYLOAD_DEPTH,
    MAX_TRACE_SEQUENCE_ITEMS,
    MAX_TRACE_STRING_LENGTH,
    TRUNCATION_MARKER_KEY,
    TRUNCATION_SUFFIX,
)
from platform.runs.truncation import truncate


def test_a_payload_within_every_bound_is_returned_unchanged() -> None:
    payload = {"pods": ["checkout-1", "checkout-2"], "restarts": 3}

    kept, removal = truncate(payload)

    assert kept == payload
    assert not removal.happened
    assert TRUNCATION_MARKER_KEY not in kept


def test_a_long_string_is_cut_and_says_so_in_the_value() -> None:
    # The value itself carries the marker, not only the summary: a silently cut
    # string is indistinguishable from a short one to whoever reads it.
    payload = {"logs": "x" * (MAX_TRACE_STRING_LENGTH * 2)}

    kept, removal = truncate(payload)

    assert kept["logs"].endswith(TRUNCATION_SUFFIX)
    assert len(kept["logs"]) < MAX_TRACE_STRING_LENGTH + len(TRUNCATION_SUFFIX) + 1
    assert removal.strings == 1
    assert kept[TRUNCATION_MARKER_KEY]["strings"] == 1


def test_a_long_sequence_keeps_its_head_and_records_what_went() -> None:
    payload = {"pods": [f"pod-{index}" for index in range(MAX_TRACE_SEQUENCE_ITEMS + 40)]}

    kept, removal = truncate(payload)

    assert len(kept["pods"]) == MAX_TRACE_SEQUENCE_ITEMS
    assert kept["pods"][0] == "pod-0"
    assert removal.items == 40
    assert kept[TRUNCATION_MARKER_KEY]["items"] == 40


def test_a_deeply_nested_branch_is_replaced_by_a_marker() -> None:
    deep: dict[str, object] = {"leaf": "value"}
    for _ in range(MAX_TRACE_PAYLOAD_DEPTH + 5):
        deep = {"nested": deep}

    kept, removal = truncate(deep)

    assert removal.branches >= 1
    assert TRUNCATION_SUFFIX.strip() in repr(kept)


def test_an_oversized_payload_is_brought_under_the_byte_cap() -> None:
    # Structural truncation alone does not bound the total: a thousand
    # short strings are each within the string cap and together are not.
    payload = {f"field-{index}": "y" * 1_000 for index in range(200)}

    kept, removal = truncate(payload)

    assert len(repr(kept).encode("utf-8")) <= MAX_TRACE_PAYLOAD_BYTES
    assert removal.happened
    assert kept[TRUNCATION_MARKER_KEY]["bytes_removed"] > 0


def test_truncation_never_invents_a_key_the_caller_already_used() -> None:
    # A payload that happens to carry the marker key gets the recorder's value,
    # because a reader must be able to trust that key to mean one thing.
    payload = {TRUNCATION_MARKER_KEY: "not mine", "logs": "x" * (MAX_TRACE_STRING_LENGTH * 2)}

    kept, _ = truncate(payload)

    assert isinstance(kept[TRUNCATION_MARKER_KEY], dict)


def test_a_non_serialisable_value_is_recorded_as_its_repr() -> None:
    # The trace has to survive whatever a capability returned. A payload that
    # raises on the way into the store is a trace that never happened.
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    kept, _ = truncate({"thing": Opaque()})

    assert kept["thing"] == "<opaque>"
