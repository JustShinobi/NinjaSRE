"""The events a live run emits, held as a record like anything else.

The stream is the one endpoint that is not a JSON body, so its fixture is the
sequence of events the mock will emit rather than a response to validate. Kept
in the same record format as everything else — same slug, same provenance, same
anonymisation — because a second format for one endpoint is a second thing that
can rot.

The event vocabulary is the platform's own, so what the console renders here is
what it will render against a deployment.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from tools.mockplane.dataset import served
from tools.mockplane.records import CapturedRecord, Provenance, Request

#: The run the live scenarios watch.
LIVE_RUN: Final = "run-0003"


def _event(sequence: int, kind: str, minutes: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": LIVE_RUN,
        "kind": kind,
        "sequence": sequence,
        "occurred_at": served.at(minutes=minutes),
        "turn_id": f"turn-0003-{max(sequence // 4, 1)}",
        "payload": payload,
    }


SHORT_STREAM: Final[tuple[dict[str, Any], ...]] = (
    _event(0, "run_started", 4, {"objective": "A hardening unit failed at boot on the primary."}),
    _event(1, "turn_started", 4, {"index": 0}),
    _event(2, "tool_called", 3, {"name": "estate.failed_units", "arguments": {"node": "node01"}}),
    _event(
        3,
        "tool_succeeded",
        3,
        {"name": "estate.failed_units", "duration_ms": 233, "units": 9},
    ),
    _event(
        4,
        "observation_recorded",
        3,
        {"detail": "nine failed units on the primary, two of them network shares"},
    ),
    _event(5, "turn_completed", 2, {"index": 0, "tokens": 1840}),
    _event(6, "turn_started", 2, {"index": 1}),
    _event(7, "tool_called", 1, {"name": "knowledge.search", "arguments": {"query": "hardening"}}),
)

#: The longer stream the live layer's reducer is proved against: enough events
#: that a reconnection lands in the middle of one rather than at a boundary.
LONG_STREAM: Final[tuple[dict[str, Any], ...]] = (
    *SHORT_STREAM,
    _event(
        8,
        "tool_succeeded",
        1,
        {"name": "knowledge.search", "duration_ms": 96, "documents": 2},
    ),
    _event(
        9,
        "hypothesis_formed",
        1,
        {"text": "The unit failed silently once before, and nothing was watching."},
    ),
    _event(10, "turn_completed", 1, {"index": 1, "tokens": 2210}),
    _event(11, "turn_started", 0, {"index": 2}),
    _event(
        12,
        "tool_called",
        0,
        {"name": "estate.storage_pressure", "arguments": {"node": "node01"}},
    ),
    _event(
        13,
        "tool_succeeded",
        0,
        {"name": "estate.storage_pressure", "duration_ms": 401, "datastores": 11},
    ),
    _event(
        14,
        "observation_recorded",
        0,
        {"detail": "two datastores answer unknown; both are shares that failed to mount"},
    ),
)


def stream_records(
    *, long: bool = False, events: Sequence[dict[str, Any]] | None = None
) -> tuple[CapturedRecord, ...]:
    """Return the stream fixture for the live run.

    ``events`` overrides the declared sequence outright, which is how the empty
    scenario gets a stream that ends immediately rather than one that never
    opens.
    """
    chosen = list(events) if events is not None else list(LONG_STREAM if long else SHORT_STREAM)
    return (
        CapturedRecord(
            slug="run-stream",
            arguments={"run_id": LIVE_RUN},
            status=200,
            body={"run_id": LIVE_RUN, "events": chosen},
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path=f"/v1/investigations/{LIVE_RUN}/stream"),
        ),
    )


__all__ = ["LIVE_RUN", "LONG_STREAM", "SHORT_STREAM", "stream_records"]
