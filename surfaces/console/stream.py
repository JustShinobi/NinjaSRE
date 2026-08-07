"""Watching a live run, and surviving the network dropping in the middle of it.

The API's stream is server-sent events, and every frame carries
``id: <run_id>:<sequence>`` (``gateway/http/streaming/sse.py``). That id is the
whole recovery mechanism: on reconnect the client presents the last one it saw
as ``Last-Event-ID``, and the server resumes from there.

Two failures are possible and neither is acceptable, so both are handled here
rather than being left to the transport.

**Losing an event.** The cursor is advanced only after an event has been handed
to the caller, never on receipt. A frame parsed and then dropped by a crash
between the two would otherwise be skipped on resume, and a missing turn in a
transcript is a transcript nobody can trust as a record.

**Repeating one.** A resume is inclusive at the server in some conditions and
exclusive in others, and a proxy may replay a buffered frame. So the reader
remembers the highest sequence it has delivered per run and refuses anything at
or below it. That check is cheap, it is local, and it makes the property hold
regardless of what the server or an intermediary chose to do.

Both together are what SC-002 asks for: an interruption during a live stream
recovers with nothing lost and nothing duplicated.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.surfaces import SSE_REPLAY_WINDOW_SECONDS

#: The separator in an event id. The run and the sequence together, because a
#: sequence alone is ambiguous across runs.
CURSOR_SEPARATOR: Final = ":"

#: How many reconnections are attempted before the reader gives up and says so.
#: Bounded because a console that retries for ever against a deployment that has
#: gone away looks identical to one that is working.
MAX_RECONNECTIONS: Final = 10


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event of a run, as the transcript renders it."""

    run_id: str
    kind: str
    sequence: int
    occurred_at: str | None = None
    turn_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        """Return the cursor a client presents to resume after this event."""
        return f"{self.run_id}{CURSOR_SEPARATOR}{self.sequence}"


@dataclass(frozen=True, slots=True)
class Frame:
    """One raw server-sent-events frame, before it is understood."""

    event_id: str = ""
    event: str = ""
    data: str = ""
    #: A comment frame, which every SSE client ignores. The keep-alive is one,
    #: and recognising it is what stops a heartbeat looking like a lost event.
    is_comment: bool = False


class StreamInterrupted(RuntimeError):
    """The stream stopped and could not be resumed within the attempt bound."""

    def __init__(self, run_id: str, attempts: int, cursor: str) -> None:
        super().__init__(
            f"the event stream for {run_id!r} could not be resumed after {attempts} "
            f"attempts; the last event seen was {cursor or '(none)'}"
        )
        self.run_id = run_id
        self.attempts = attempts
        self.cursor = cursor


@runtime_checkable
class EventSource(Protocol):
    """Whatever produces SSE lines for one run, from a cursor.

    A protocol rather than a concrete HTTP client, for the same reason
    ``surfaces/cli/client.py`` states a protocol: it is the seam, and it is what
    lets an induced network interruption be a test rather than a deployment.
    """

    def open(self, run_id: str, *, last_event_id: str = "") -> AsyncIterator[str]:
        """Return the raw SSE lines for ``run_id``, resuming after ``last_event_id``."""


@dataclass(slots=True)
class Cursor:
    """The last event delivered for a run, and the guard against re-delivering it.

    Deliberately per-run rather than global. A console watching two runs at once
    has two independent sequences, and a single high-water mark would silently
    suppress the second run's early events.
    """

    #: How long a disconnected client may reconnect and still resume, per the
    #: deployment's own replay window. Held here so a caller that has been away
    #: longer can be told to reload rather than shown a hole.
    replay_window_seconds: float = SSE_REPLAY_WINDOW_SECONDS
    _delivered: dict[str, int] = field(default_factory=dict)

    def last_event_id(self, run_id: str) -> str:
        """Return the cursor to present on reconnect, or the empty string."""
        sequence = self._delivered.get(run_id)
        return "" if sequence is None else f"{run_id}{CURSOR_SEPARATOR}{sequence}"

    def is_fresh(self, event: StreamEvent) -> bool:
        """Return whether ``event`` has not already been delivered for its run."""
        return event.sequence > self._delivered.get(event.run_id, -1)

    def record(self, event: StreamEvent) -> None:
        """Note that ``event`` has been delivered.

        Called *after* the caller has it, never on receipt. An event recorded and
        then lost is an event a resume would skip.
        """
        current = self._delivered.get(event.run_id)
        if current is None or event.sequence > current:
            self._delivered[event.run_id] = event.sequence


def parse_frames(lines: Iterable[str]) -> Iterator[Frame]:
    """Yield one ``Frame`` per blank-line-terminated block of SSE lines.

    Written against lines rather than bytes so a reader can be driven by a list
    in a test and by a socket in production without a second parser.
    """
    event_id = ""
    event = ""
    data: list[str] = []
    comment = False

    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if line == "":
            if data or event_id or event or comment:
                yield Frame(
                    event_id=event_id, event=event, data="\n".join(data), is_comment=comment
                )
            event_id, event, data, comment = "", "", [], False
            continue
        if line.startswith(":"):
            comment = True
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "id":
            event_id = value
        elif name == "event":
            event = value
        elif name == "data":
            data.append(value)

    if data or event_id or event or comment:
        yield Frame(event_id=event_id, event=event, data="\n".join(data), is_comment=comment)


def event_of(frame: Frame) -> StreamEvent | None:
    """Return the event ``frame`` carries, or ``None`` if it carries none.

    A comment frame, an empty frame, and a frame whose data is not the object
    this API sends all return ``None``. A malformed frame is skipped rather than
    raised on: an unreadable event during an incident should cost the reader one
    line of the transcript, not the rest of the stream.
    """
    if frame.is_comment or not frame.data:
        return None
    try:
        document = json.loads(frame.data)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None

    run_id = str(document.get("run_id", ""))
    sequence = document.get("sequence")
    if not run_id or not isinstance(sequence, int):
        return None

    payload = document.get("payload")
    return StreamEvent(
        run_id=run_id,
        kind=str(document.get("kind", "")),
        sequence=sequence,
        occurred_at=document.get("occurred_at"),
        turn_id=document.get("turn_id"),
        payload=dict(payload) if isinstance(payload, dict) else {},
    )


def parse_cursor(event_id: str) -> tuple[str, int] | None:
    """Return the ``(run_id, sequence)`` an event id spells, or ``None``."""
    run_id, separator, raw = event_id.rpartition(CURSOR_SEPARATOR)
    if not separator or not run_id:
        return None
    try:
        return run_id, int(raw)
    except ValueError:
        return None


@dataclass(slots=True)
class RunStream:
    """A live subscription to one run, reconnecting where it left off.

    The reconnection loop is the component: opening a stream is the transport's
    job, and deciding what to present on reopening — and what to refuse when the
    server sends it again — is this.
    """

    source: EventSource
    cursor: Cursor = field(default_factory=Cursor)
    max_reconnections: int = MAX_RECONNECTIONS
    #: How many times this stream actually had to reconnect. Read by the page so
    #: it can say "reconnected" rather than leaving a gap the reader wonders
    #: about.
    reconnections: int = 0

    async def events(self, run_id: str) -> AsyncIterator[StreamEvent]:
        """Yield ``run_id``'s events, in sequence order, exactly once each.

        Raises:
            StreamInterrupted: the stream could not be resumed within the bound.
        """
        attempts = 0
        while True:
            delivered_this_attempt = False
            try:
                async for line_block in _blocks(
                    self.source.open(run_id, last_event_id=self.cursor.last_event_id(run_id))
                ):
                    event = event_of(line_block)
                    if event is None or not self.cursor.is_fresh(event):
                        continue
                    yield event
                    self.cursor.record(event)
                    delivered_this_attempt = True
                return
            except (ConnectionError, TimeoutError, OSError):
                attempts = 0 if delivered_this_attempt else attempts + 1
                self.reconnections += 1
                if attempts > self.max_reconnections:
                    raise StreamInterrupted(
                        run_id, attempts, self.cursor.last_event_id(run_id)
                    ) from None


async def _blocks(lines: AsyncIterator[str]) -> AsyncIterator[Frame]:
    """Yield one frame per blank-line-terminated block of an async line stream."""
    pending: list[str] = []
    async for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        pending.append(line)
        if line == "":
            for frame in parse_frames(pending):
                yield frame
            pending = []
    if pending:
        for frame in parse_frames([*pending, ""]):
            yield frame


__all__ = [
    "CURSOR_SEPARATOR",
    "MAX_RECONNECTIONS",
    "Cursor",
    "EventSource",
    "Frame",
    "RunStream",
    "StreamEvent",
    "StreamInterrupted",
    "event_of",
    "parse_cursor",
    "parse_frames",
]
