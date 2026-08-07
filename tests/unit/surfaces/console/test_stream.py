"""Live streaming, and the interruption it has to survive (SC-002).

The interruption is induced rather than simulated at the edges: the source
raises a real ``ConnectionError`` part-way through, exactly as a dropped socket
would, and the reader is asserted to have delivered every event once and no
event twice across the seam.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from surfaces.console.stream import (
    Cursor,
    Frame,
    RunStream,
    StreamEvent,
    StreamInterrupted,
    event_of,
    parse_cursor,
    parse_frames,
)

pytestmark = pytest.mark.anyio

RUN = "run-42"


def _frame(sequence: int, *, run_id: str = RUN, kind: str = "thought") -> str:
    """Return one SSE frame exactly as ``gateway/http/streaming/sse.py`` writes it."""
    body = (
        f'{{"kind":"{kind}","occurred_at":"2026-05-01T08:00:00+00:00",'
        f'"payload":{{"text":"step {sequence}"}},"run_id":"{run_id}",'
        f'"sequence":{sequence},"turn_id":"t-1"}}'
    )
    return f"id: {run_id}:{sequence}\nevent: {kind}\ndata: {body}\n\n"


class ScriptedSource:
    """An event source that drops the connection at a chosen point, once.

    Holds what each open was asked to resume from, because "did the client
    actually present the cursor" is half of what SC-002 is about — a reader that
    reconnected from the beginning and then de-duplicated would pass a
    lost-and-duplicated assertion while re-downloading the whole run.
    """

    def __init__(self, *, total: int, drop_after: int, drops: int = 1) -> None:
        self.total = total
        self.drop_after = drop_after
        self.drops_remaining = drops
        self.opened_with: list[str] = []

    async def _lines(self, run_id: str, last_event_id: str) -> AsyncIterator[str]:
        self.opened_with.append(last_event_id)
        resume_from = 0
        parsed = parse_cursor(last_event_id)
        if parsed is not None:
            resume_from = parsed[1] + 1

        for delivered, sequence in enumerate(range(resume_from, self.total)):
            if self.drops_remaining > 0 and delivered == self.drop_after:
                self.drops_remaining -= 1
                raise ConnectionError("the socket went away")
            for line in _frame(sequence).splitlines(keepends=True):
                yield line

    def open(self, run_id: str, *, last_event_id: str = "") -> AsyncIterator[str]:
        return self._lines(run_id, last_event_id)


class AlwaysFailing:
    """A source that never yields anything and always drops."""

    def __init__(self) -> None:
        self.opens = 0

    async def _lines(self) -> AsyncIterator[str]:
        self.opens += 1
        raise ConnectionError("nothing is listening")
        yield ""  # pragma: no cover - unreachable, required to make this a generator

    def open(self, run_id: str, *, last_event_id: str = "") -> AsyncIterator[str]:
        return self._lines()


class ReplayingSource:
    """A source that re-sends the frames the client already had on reconnect.

    What a buffering proxy does, and what an inclusive server-side resume does.
    The reader is expected to refuse them.
    """

    def __init__(self, *, total: int, drop_after: int) -> None:
        self.total = total
        self.drop_after = drop_after
        self.dropped = False

    async def _lines(self) -> AsyncIterator[str]:
        stop = self.total if self.dropped else self.drop_after
        for sequence in range(stop):
            for line in _frame(sequence).splitlines(keepends=True):
                yield line
        if not self.dropped:
            self.dropped = True
            raise ConnectionError("dropped, and the proxy will replay from the top")

    def open(self, run_id: str, *, last_event_id: str = "") -> AsyncIterator[str]:
        return self._lines()


# --- Frame parsing ------------------------------------------------------------


def test_a_frame_is_parsed_into_its_id_event_and_data() -> None:
    frames = list(parse_frames(_frame(3).splitlines(keepends=True)))

    assert len(frames) == 1
    assert frames[0].event_id == f"{RUN}:3"
    assert frames[0].event == "thought"


def test_a_heartbeat_comment_is_recognised_and_carries_no_event() -> None:
    frames = list(parse_frames([": heartbeat\n", "\n"]))

    assert frames[0].is_comment
    assert event_of(frames[0]) is None


def test_a_frame_whose_data_is_not_json_costs_one_line_rather_than_the_stream() -> None:
    assert event_of(Frame(event_id="x:1", data="{not json")) is None


def test_a_frame_missing_a_sequence_is_skipped_rather_than_guessed_at() -> None:
    assert event_of(Frame(event_id="x:1", data='{"run_id":"x"}')) is None


def test_an_event_id_is_the_run_and_the_sequence_because_a_sequence_alone_is_ambiguous() -> None:
    assert parse_cursor(f"{RUN}:7") == (RUN, 7)
    assert parse_cursor("malformed") is None
    assert parse_cursor("") is None


def test_an_event_reports_the_cursor_a_client_would_present_after_it() -> None:
    event = StreamEvent(run_id=RUN, kind="thought", sequence=9)

    assert event.event_id == f"{RUN}:9"


# --- The cursor ---------------------------------------------------------------


def test_a_cursor_starts_empty_so_a_first_connection_asks_for_everything() -> None:
    assert Cursor().last_event_id(RUN) == ""


def test_a_cursor_advances_only_once_an_event_has_actually_been_delivered() -> None:
    cursor = Cursor()
    event = StreamEvent(run_id=RUN, kind="thought", sequence=4)

    assert cursor.last_event_id(RUN) == ""
    cursor.record(event)
    assert cursor.last_event_id(RUN) == f"{RUN}:4"


def test_a_cursor_refuses_an_event_it_has_already_delivered() -> None:
    cursor = Cursor()
    cursor.record(StreamEvent(run_id=RUN, kind="thought", sequence=4))

    assert not cursor.is_fresh(StreamEvent(run_id=RUN, kind="thought", sequence=4))
    assert not cursor.is_fresh(StreamEvent(run_id=RUN, kind="thought", sequence=3))
    assert cursor.is_fresh(StreamEvent(run_id=RUN, kind="thought", sequence=5))


def test_two_runs_watched_at_once_keep_independent_cursors() -> None:
    cursor = Cursor()
    cursor.record(StreamEvent(run_id="run-a", kind="thought", sequence=50))

    assert cursor.is_fresh(StreamEvent(run_id="run-b", kind="thought", sequence=0))
    assert cursor.last_event_id("run-b") == ""


# --- SC-002: nothing lost, nothing duplicated ---------------------------------


async def test_an_interrupted_stream_loses_no_event_and_repeats_none() -> None:
    source = ScriptedSource(total=20, drop_after=7)
    stream = RunStream(source=source)

    seen = [event.sequence async for event in stream.events(RUN)]

    assert seen == list(range(20))
    assert len(seen) == len(set(seen))
    assert stream.reconnections == 1


async def test_the_reconnection_presents_the_last_event_actually_delivered() -> None:
    source = ScriptedSource(total=20, drop_after=7)

    async for _ in RunStream(source=source).events(RUN):
        pass

    assert source.opened_with == ["", f"{RUN}:6"]


async def test_several_interruptions_in_one_run_still_lose_and_repeat_nothing() -> None:
    source = ScriptedSource(total=30, drop_after=4, drops=3)
    stream = RunStream(source=source)

    seen = [event.sequence async for event in stream.events(RUN)]

    assert seen == list(range(30))
    assert stream.reconnections == 3


async def test_a_proxy_replaying_frames_the_client_already_had_delivers_them_once() -> None:
    stream = RunStream(source=ReplayingSource(total=12, drop_after=5))

    seen = [event.sequence async for event in stream.events(RUN)]

    assert seen == list(range(12))


async def test_a_deployment_that_never_answers_is_reported_rather_than_retried_for_ever() -> None:
    source = AlwaysFailing()
    stream = RunStream(source=source, max_reconnections=3)

    with pytest.raises(StreamInterrupted, match="could not be resumed"):
        async for _ in stream.events(RUN):
            pass

    assert source.opens == 4


async def test_progress_resets_the_attempt_count_so_a_long_run_is_not_given_up_on() -> None:
    source = ScriptedSource(total=40, drop_after=2, drops=8)
    stream = RunStream(source=source, max_reconnections=3)

    seen = [event.sequence async for event in stream.events(RUN)]

    assert seen == list(range(40))
