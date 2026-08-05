"""The stream is a record, not a progress bar.

Two properties are asserted here, and the feature rests on both. Every event
survives a JSON round trip, because an event that cannot be written down cannot
be replayed; and replaying the persisted events reconstructs the investigation
view, because a console showing something the trace cannot reproduce
is showing something nobody can audit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core.pipeline.streaming import (
    EventStream,
    PipelineEvent,
    PipelineEventKind,
    RecordingSink,
    replay,
)
from core.state.types import StageName

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _BrokenSink:
    """A sink that always fails, as a disconnected browser does."""

    def __init__(self) -> None:
        self.attempts = 0

    async def emit(self, event: PipelineEvent) -> None:
        self.attempts += 1
        raise ConnectionResetError("the client went away")


def _ticking_clock() -> object:
    moments = iter(AT + timedelta(seconds=index) for index in range(1000))
    return lambda: next(moments)


async def _investigation(stream: EventStream) -> None:
    """Emit one complete investigation's worth of events."""
    await stream.stage_start(StageName.INTAKE)
    await stream.stage_end(StageName.INTAKE, detail={"classification": "incident"})
    await stream.stage_start(StageName.GATHER_EVIDENCE)
    await stream.emit(
        PipelineEvent(kind=PipelineEventKind.THOUGHT, text="check the pod's recent events")
    )
    await stream.emit(
        PipelineEvent(
            kind=PipelineEventKind.TOOL_START,
            capability="kubernetes_pod_events",
            call_id="c1",
        )
    )
    await stream.emit(
        PipelineEvent(
            kind=PipelineEventKind.TOOL_END,
            capability="kubernetes_pod_events",
            call_id="c1",
            text="3 OOMKilled events",
        )
    )
    await stream.emit(PipelineEvent(kind=PipelineEventKind.EVIDENCE, evidence_id="e1"))
    await stream.emit(PipelineEvent(kind=PipelineEventKind.SUBAGENT_START, subagent="log_analyst"))
    await stream.emit(
        PipelineEvent(
            kind=PipelineEventKind.SUBAGENT_END,
            subagent="log_analyst",
            text="the errors start at 12:04",
        )
    )
    await stream.emit(
        PipelineEvent(kind=PipelineEventKind.QUESTION, text="was there a deploy at 12:00?")
    )
    await stream.emit(
        PipelineEvent(kind=PipelineEventKind.APPROVAL_REQUEST, text="restart the deployment")
    )
    await stream.emit(
        PipelineEvent(kind=PipelineEventKind.MESSAGE_QUEUED, text="check the canary too")
    )
    await stream.stage_end(StageName.GATHER_EVIDENCE)
    await stream.result("the checkout container exceeded its memory limit")


# -- serialisation ------------------------------------------------------------


@pytest.mark.parametrize("kind", list(PipelineEventKind))
def test_every_event_kind_round_trips_through_json(kind: PipelineEventKind) -> None:
    event = PipelineEvent(
        kind=kind,
        run_id="run-1",
        sequence=7,
        occurred_at=AT,
        stage=StageName.GATHER_EVIDENCE,
        text="something happened",
        capability="datadog_log_statistics",
        call_id="c1",
        subagent="log_analyst",
        evidence_id="e1",
        failed=kind is PipelineEventKind.ERROR,
        detail={"reason": "because"},
    )

    assert PipelineEvent.from_json(event.to_json()) == event


def test_an_event_without_a_stage_round_trips_as_having_none() -> None:
    event = PipelineEvent(kind=PipelineEventKind.RESULT, occurred_at=AT, text="done")

    assert PipelineEvent.from_record(json.loads(event.to_json())).stage is None


# -- emission -----------------------------------------------------------------


async def test_emission_stamps_the_run_the_sequence_and_the_time() -> None:
    sink = RecordingSink()
    stream = EventStream("run-1", (sink,), clock=_ticking_clock())  # type: ignore[arg-type]

    await stream.stage_start(StageName.INTAKE)
    await stream.stage_end(StageName.INTAKE)

    assert [event.sequence for event in sink.events] == [1, 2]
    assert {event.run_id for event in sink.events} == {"run-1"}
    assert sink.events[0].occurred_at < sink.events[1].occurred_at


async def test_a_sink_that_fails_does_not_stop_the_others_or_the_run() -> None:
    """A disconnected browser must not end an incident investigation."""
    broken = _BrokenSink()
    good = RecordingSink()
    stream = EventStream("run-1", (broken, good))

    await stream.stage_start(StageName.INTAKE)
    await stream.result("done")

    assert broken.attempts == 2
    assert [event.kind for event in good.events] == [
        PipelineEventKind.STAGE_START,
        PipelineEventKind.RESULT,
    ]


# -- replay -------------------------------------------------------------------


async def test_replaying_the_persisted_events_reconstructs_the_investigation() -> None:
    sink = RecordingSink()
    stream = EventStream("run-1", (sink,), clock=_ticking_clock())  # type: ignore[arg-type]

    await _investigation(stream)

    # Through the store, not through the objects: what a surface replays is
    # what was written down, and a field that does not survive the record is
    # not in the trace however carefully it was emitted.
    persisted = [PipelineEvent.from_record(record) for record in sink.records()]
    view = replay(persisted)

    assert view.run_id == "run-1"
    assert [found.stage for found in view.stages] == [
        StageName.INTAKE,
        StageName.GATHER_EVIDENCE,
    ]
    assert view.stage(StageName.INTAKE) is not None
    assert view.stage(StageName.INTAKE).completed  # type: ignore[union-attr]
    assert view.stage(StageName.INTAKE).detail == {"classification": "incident"}  # type: ignore[union-attr]
    assert view.thoughts == ("check the pod's recent events",)
    assert [call.capability for call in view.tool_calls] == ["kubernetes_pod_events"]
    assert view.tool_calls[0].completed
    assert view.tool_calls[0].summary == "3 OOMKilled events"
    assert [agent.name for agent in view.subagents] == ["log_analyst"]
    assert view.subagents[0].headline == "the errors start at 12:04"
    assert view.evidence_ids == ("e1",)
    assert view.questions == ("was there a deploy at 12:00?",)
    assert view.approval_requests == ("restart the deployment",)
    assert view.queued_messages == ("check the canary too",)
    assert view.result == "the checkout container exceeded its memory limit"
    assert not view.failed


async def test_replay_orders_by_sequence_not_by_arrival() -> None:
    sink = RecordingSink()
    stream = EventStream("run-1", (sink,), clock=_ticking_clock())  # type: ignore[arg-type]
    await _investigation(stream)

    shuffled = list(reversed(sink.events))

    assert replay(shuffled) == replay(sink.events)


async def test_an_error_event_marks_its_stage_failed() -> None:
    sink = RecordingSink()
    stream = EventStream("run-1", (sink,))

    await stream.stage_start(StageName.DIAGNOSE)
    await stream.error(StageName.DIAGNOSE, "the provider timed out")

    view = replay(sink.events)

    assert view.failed
    assert view.errors == ("the provider timed out",)
    assert view.stage(StageName.DIAGNOSE) is not None
    assert view.stage(StageName.DIAGNOSE).failed  # type: ignore[union-attr]


def test_an_unplaceable_event_is_recorded_rather_than_dropped() -> None:
    """A hole in the trace that nobody can see is the one nobody finds."""
    view = replay([PipelineEvent(kind=PipelineEventKind.STAGE_START, sequence=1)])

    assert view.stages == ()
    assert len(view.errors) == 1
    assert "stage_start" in view.errors[0]
