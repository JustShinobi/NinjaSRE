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


#: The eight-event backbone both streams below build from. Kept apart from
#: ``SHORT_STREAM`` itself so that inserting the stage milestones into the
#: populated scenario's own stream, below, never reaches into ``LONG_STREAM``:
#: the two are the same run, but only one of them is asked to also carry the
#: stage boundaries, and a shared literal would have carried them into both.
_BASE_SHORT_STREAM: Final[tuple[dict[str, Any], ...]] = (
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


def _stage_milestone(occurred_at: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return one ``stage_completed`` event for the live run, sequence unset.

    Unlike ``_event``, this carries no ``turn_id``: a stage boundary sits
    between turns rather than inside one, the same reason ``_replay_stage``
    never nests a stage's own record under a turn either. ``sequence`` is a
    placeholder ``0``, corrected by ``_resequenced`` once this milestone's
    final position among its neighbours is known.

    ``occurred_at`` still comes from ``served.at``, ``seconds`` included: two of
    the three stage boundaries below land a second apart from the events they
    sit beside, and the anonymisation pipeline shifts every timestamp in this
    document by the same offset afterwards — a literal instant here would be
    shifted twice over, once by nothing and once by that offset, and would
    land nowhere near its neighbours.
    """
    return {
        "run_id": LIVE_RUN,
        "kind": "stage_completed",
        "sequence": 0,
        "occurred_at": occurred_at,
        "turn_id": None,
        "payload": payload,
    }


def _resequenced(events: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return ``events`` in the given order, ``sequence`` renumbered to match position.

    Every other field stays exactly as given. This is what lets a milestone be
    spliced into an already-declared stream: its neighbours keep the turn
    identity and timestamp they were written with, and only the
    position-derived field moves.
    """
    return tuple({**event, "sequence": index} for index, event in enumerate(events))


#: The three stage boundaries the pipeline has already crossed by the time
#: this run's stream opens — the same three ``served._STAGES["run-0003"]``
#: declares for the replay, so a viewer watching live and one replaying later
#: are told the same three things happened. Declared here rather than derived
#: from that mapping: the replay's own ``intake`` records one model call, and
#: this stream's boundary for the same stage does not, which is what the
#: stream a real recorder would have written before the model that classified
#: this incident had answered — the boundary fires, and the call it counted
#: lands a moment after.
_STAGE_MILESTONES: Final[tuple[dict[str, Any], ...]] = (
    _stage_milestone(
        served.at(minutes=4),
        {
            "stage": "resolve_integrations",
            "finding": "6 capabilities available on this team",
            "duration_ms": 175,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "failed": False,
        },
    ),
    _stage_milestone(
        served.at(minutes=4, seconds=-1),
        {
            "stage": "intake",
            "finding": "A new incident, not a repeat of one already open",
            "duration_ms": 1260,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "failed": False,
        },
    ),
    _stage_milestone(
        served.at(minutes=4, seconds=-2),
        {
            "stage": "plan_evidence",
            "finding": "3 capabilities shortlisted, best first",
            "duration_ms": 55,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "failed": False,
        },
    ),
)

#: The fourth stage boundary, appended rather than declared alongside the
#: three above: the gathering stage has not finished in this scenario's own
#: replay (`served._STAGES["run-0003"]` stops at ``plan_evidence``), so this
#: one event exists only on the stream, for the same reason the module
#: docstring above gives for the whole file — a local test watches the active
#: stage move without a reload, which needs one more boundary to move to and
#: not a fourth entry the replay would have to also claim.
_GATHER_STAGE_MILESTONE: Final[dict[str, Any]] = _stage_milestone(
    served.at(minutes=-10),
    {
        "stage": "gather_evidence",
        "finding": "3 observations gathered",
        "duration_ms": 45000,
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "failed": False,
    },
)

#: The populated scenario's own stream: the eight-event backbone with the
#: pipeline's stage boundaries layered in, three before the first turn and one
#: after the last recorded event, exactly where the run's own replay says the
#: pipeline had reached.
SHORT_STREAM: Final[tuple[dict[str, Any], ...]] = _resequenced(
    (
        _BASE_SHORT_STREAM[0],
        *_STAGE_MILESTONES,
        *_BASE_SHORT_STREAM[1:],
        _GATHER_STAGE_MILESTONE,
    )
)

#: The longer stream the live layer's reducer is proved against: enough events
#: that a reconnection lands in the middle of one rather than at a boundary.
#: Built from the backbone directly, not from ``SHORT_STREAM``, so the stage
#: milestones that belong to the populated scenario alone do not ride along.
LONG_STREAM: Final[tuple[dict[str, Any], ...]] = (
    *_BASE_SHORT_STREAM,
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


def deployment_stream_records() -> tuple[CapturedRecord, ...]:
    """Return the coverage placeholder for the deployment-wide channel.

    Unlike ``run-stream`` above, ``tools.mockplane.server.MockPlane`` never
    actually reads this record: the deployment channel is session-scoped —
    every event on it exists because a write during that same session put it
    there (``MockPlane._publish_deployment_event``), and nothing in a fixture
    file could describe a session that has not happened yet. This exists
    only so the endpoint the console consumes has a record at all — the
    coverage suite (`tests/contract/fixtures/test_dataset_contract.py`)
    requires one for every declared `ConsoleEndpoint`, streaming or not —
    and it is honest about carrying nothing: a fresh connection to a fresh
    session sees no backlog either, in the real deployment and here alike.
    """
    return (
        CapturedRecord(
            slug="deployment-stream",
            arguments={},
            status=200,
            body={"events": []},
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path="/v1/events/stream"),
        ),
    )


__all__ = [
    "LIVE_RUN",
    "LONG_STREAM",
    "SHORT_STREAM",
    "deployment_stream_records",
    "stream_records",
]
