"""One channel for what changed across a deployment, not what any of it is now.

A run's own stream (``platform.runs.stream``) answers "what is this run doing".
Nothing answered "what changed anywhere" without a page reload — a list screen
had no way to hear that a run started, an incident opened, or a decision was
made, so it waited for a timer. This module is the broker behind that channel:
a short, in-process memory of the last few events, fanned out live to whoever
is attached, and deliberately not a durable log.

**Not durable, on purpose.** A frame here carries only an identity — a run id,
an incident id, the ids a decision is known by — never the state itself. The
state is still read from the routes that already own it (`GET /v1/runs`,
`GET /v1/incidents`, `GET /v1/proposals`, ...), and a client that receives an
event does nothing with it beyond asking one of those routes to be read again.
That is what makes losing an event survivable: a gap costs one extra read of
data that was already true, never a fact that only ever existed on the wire.
The corollary is ``resync`` — a control frame with no payload, sent instead of
best-effort replay the moment this broker cannot honestly say it has
everything a reconnecting client missed, exactly as a second event log kept in
step with the routes by hand would have to be built to avoid.

**Epoch, not a durable position.** Every construction of this broker — which
happens once per process, at boot — gets a fresh, random epoch. A cursor names
an epoch and a sequence within it; a cursor from a different epoch names a
process that is no longer the one being asked, and reconnecting into it is
answered with ``resync`` rather than a silent restart at sequence zero, which
would look like nothing had ever happened.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from config.constants.runs import DEPLOYMENT_STREAM_BUFFER_EVENTS
from platform.observability.logging import get_logger
from platform.runs.events import RunEvent, TraceEventKind
from platform.runs.stream import RunEventBroker

logger = get_logger(__name__)

#: Separates the epoch from the sequence in a deployment cursor's wire form —
#: the same character `platform.runs.cursor.Cursor` uses, for the same reason:
#: neither half is one an SSE `Last-Event-ID` header would mangle.
_SEPARATOR: Final = ":"


class DeploymentCursorError(ValueError):
    """A deployment cursor string is not one."""


class DeploymentScope(StrEnum):
    """What kind of thing a deployment event is about."""

    RUN = "run"
    INCIDENT = "incident"
    DECISION = "decision"
    #: A frame about the channel itself, never about the deployment's data.
    #: ``resync`` is the only kind carried at this scope today.
    CONTROL = "control"


class DeploymentEventKind(StrEnum):
    """The ten kinds of frame this channel ever carries, and no others.

    Closed on purpose, the same reason `TraceEventKind` is: a kind nobody named
    here is a kind the console cannot react to, so a new one is a deliberate
    addition to this enum rather than a string a publisher invents.
    """

    RUN_STARTED = "run_started"
    STAGE_COMPLETED = "stage_completed"
    ATTENTION_CHANGED = "attention_changed"
    RUN_FINISHED = "run_finished"
    INCIDENT_OPENED = "incident_opened"
    INCIDENT_CLOSED = "incident_closed"
    DECISION_PROPOSED = "decision_proposed"
    DECISION_EXPIRED = "decision_expired"
    DECISION_DECIDED = "decision_decided"
    RESYNC = "resync"


#: Which payload keys each scope may carry — an allowlist, not a suggestion.
#: `DeploymentEvent.__post_init__` refuses anything outside it, which is what
#: keeps this channel from becoming a second way to leak a run's title, an
#: incident's summary, or a decision's document onto the wire: only the ids a
#: reader would use to ask a read route for the truth ever cross it.
_ALLOWED_PAYLOAD_KEYS: Final[Mapping[DeploymentScope, frozenset[str]]] = {
    DeploymentScope.RUN: frozenset({"run_id"}),
    DeploymentScope.INCIDENT: frozenset({"incident_id"}),
    #: A decision may be known by the queue that reviews it (`proposal_id`) or
    #: by the live interaction an in-run approval raised (`interaction_id`), or
    #: both — never by neither, and never by anything else.
    DeploymentScope.DECISION: frozenset({"proposal_id", "interaction_id"}),
    DeploymentScope.CONTROL: frozenset(),
}

#: The kinds that belong to each scope. Also an allowlist: publishing
#: `run_started` at `scope="incident"` is a defect in the caller, and this
#: catches it at construction rather than leaving it for whichever console
#: reducer meets the mismatch first.
_KINDS_BY_SCOPE: Final[Mapping[DeploymentScope, frozenset[DeploymentEventKind]]] = {
    DeploymentScope.RUN: frozenset(
        {
            DeploymentEventKind.RUN_STARTED,
            DeploymentEventKind.STAGE_COMPLETED,
            DeploymentEventKind.ATTENTION_CHANGED,
            DeploymentEventKind.RUN_FINISHED,
        }
    ),
    DeploymentScope.INCIDENT: frozenset(
        {DeploymentEventKind.INCIDENT_OPENED, DeploymentEventKind.INCIDENT_CLOSED}
    ),
    DeploymentScope.DECISION: frozenset(
        {
            DeploymentEventKind.DECISION_PROPOSED,
            DeploymentEventKind.DECISION_EXPIRED,
            DeploymentEventKind.DECISION_DECIDED,
        }
    ),
    DeploymentScope.CONTROL: frozenset({DeploymentEventKind.RESYNC}),
}


@dataclass(frozen=True, slots=True)
class DeploymentEvent:
    """One frame of the deployment channel: an identity, never a state."""

    scope: DeploymentScope
    kind: DeploymentEventKind
    sequence: int
    occurred_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in _KINDS_BY_SCOPE[self.scope]:
            raise ValueError(f"{self.kind.value!r} does not belong to scope {self.scope.value!r}")
        allowed = _ALLOWED_PAYLOAD_KEYS[self.scope]
        extra = set(self.payload) - allowed
        if extra:
            raise ValueError(
                f"a {self.scope.value!r} event's payload may only carry "
                f"{sorted(allowed) or 'nothing'}; got the extra key(s) {sorted(extra)}"
            )


@dataclass(frozen=True, slots=True)
class DeploymentCursor:
    """Where one subscriber has got to on the deployment channel.

    An epoch and a position within it — the same shape as a run's own
    `platform.runs.cursor.Cursor`, with the run id replaced by the epoch this
    broker was built with, because the deployment channel has no single run to
    be a position within.
    """

    epoch: str
    sequence: int

    @classmethod
    def parse(cls, raw: str) -> DeploymentCursor:
        """Return the cursor ``raw`` encodes, or raise ``DeploymentCursorError``."""
        epoch, separator, position = raw.rpartition(_SEPARATOR)
        if not separator or not epoch:
            raise DeploymentCursorError(
                f"a deployment cursor is 'epoch{_SEPARATOR}sequence', not {raw!r}."
            )
        try:
            return cls(epoch=epoch, sequence=int(position))
        except ValueError as broken:
            raise DeploymentCursorError(f"{position!r} is not a stream position.") from broken

    def __str__(self) -> str:
        return f"{self.epoch}{_SEPARATOR}{self.sequence}"


class DeploymentSubscriberTooSlow(RuntimeError):
    """A subscriber to the deployment channel fell behind its buffer.

    Recoverable the same way a run's own overrun subscriber is: the connection
    ends, the client reconnects, and its cursor is judged against the buffer
    again — most likely answered with ``resync``, since falling behind this
    channel's small buffer is itself evidence the gap has outrun what memory
    alone can repair.
    """


@dataclass(slots=True)
class _Subscription:
    """One client's live attachment to the deployment channel."""

    _queue: asyncio.Queue[DeploymentEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEPLOYMENT_STREAM_BUFFER_EVENTS)
    )
    _overflowed: bool = False
    _closed: bool = False

    def offer(self, event: DeploymentEvent) -> None:
        """Enqueue ``event``, or mark this subscriber fallen behind. Never blocks."""
        if self._closed or self._overflowed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._overflowed = True
            logger.warning("runs.deployment_subscriber_dropped", buffered=self._queue.qsize())

    def close(self) -> None:
        self._closed = True

    @property
    def overflowed(self) -> bool:
        return self._overflowed

    async def drain(self) -> AsyncIterator[DeploymentEvent]:
        """Yield everything buffered for this subscriber, in order."""
        while not self._queue.empty():
            if self._overflowed:
                raise DeploymentSubscriberTooSlow(f"{self._queue.qsize()} events buffered")
            yield self._queue.get_nowait()


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class DeploymentEventBroker:
    """In-process fan-out for the deployment channel, with a short memory.

    The memory is what lets a reconnecting client be served without a durable
    log: the last `DEPLOYMENT_STREAM_BUFFER_EVENTS` events are kept, and a
    cursor this broker's own memory cannot honestly cover — a different epoch,
    or a position older than the oldest buffered event — is answered with
    `resync` rather than a silent gap or a fabricated replay.
    """

    #: Identifies this broker's lifetime in the process. A fresh one every
    #: construction, which happens once per process at boot — never per
    #: request, never per subscriber.
    epoch: str = field(default_factory=lambda: uuid.uuid4().hex)
    _sequence: int = field(default=0, init=False, repr=False)
    _buffer: deque[DeploymentEvent] = field(init=False, repr=False)
    _subscribers: list[_Subscription] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = deque(maxlen=DEPLOYMENT_STREAM_BUFFER_EVENTS)

    @property
    def subscriber_count(self) -> int:
        """Return how many clients are attached right now."""
        return len(self._subscribers)

    async def publish(
        self, *, scope: DeploymentScope, kind: DeploymentEventKind, payload: Mapping[str, Any]
    ) -> DeploymentEvent:
        """Assign the next sequence to one fact, remember it, and deliver it live.

        Delivery never waits on a subscriber: `_Subscription.offer` does not
        block, so one slow reader cannot make this call — which every write
        path this feature taps runs on — wait on it.
        """
        self._sequence += 1
        event = DeploymentEvent(
            scope=scope, kind=kind, sequence=self._sequence, occurred_at=_utc_now(), payload=payload
        )
        self._buffer.append(event)
        for subscription in self._subscribers:
            subscription.offer(event)
        return event

    def _coverable(self, position: int) -> bool:
        """Return whether this broker's memory can serve everything after ``position``."""
        if position >= self._sequence:
            return True
        if not self._buffer:
            return False
        return position >= self._buffer[0].sequence - 1

    def attach(
        self, cursor: DeploymentCursor | None = None
    ) -> tuple[_Subscription, tuple[DeploymentEvent, ...]]:
        """Register a live subscriber and return it with whatever it should see first.

        A first connection (``cursor`` is ``None``) needs nothing backfilled: the
        page that opened the channel already read its own current state. A
        reconnection this broker's memory can cover is backfilled from the
        buffer. A reconnection it cannot cover — a different epoch, or a
        position older than the buffer's oldest entry — gets exactly one
        `resync` event instead, at the current tip, so the client refreshes once
        and then watches forward from here rather than from a hole this memory
        cannot honestly fill.
        """
        subscription = _Subscription()
        self._subscribers.append(subscription)

        if cursor is None:
            return subscription, ()

        if cursor.epoch == self.epoch and self._coverable(cursor.sequence):
            backlog = tuple(event for event in self._buffer if event.sequence > cursor.sequence)
            return subscription, backlog

        resync = DeploymentEvent(
            scope=DeploymentScope.CONTROL,
            kind=DeploymentEventKind.RESYNC,
            sequence=self._sequence,
            occurred_at=_utc_now(),
            payload={},
        )
        return subscription, (resync,)

    def detach(self, subscription: _Subscription) -> None:
        """Remove ``subscription`` and stop delivering to it."""
        subscription.close()
        if subscription in self._subscribers:
            self._subscribers.remove(subscription)


#: The `TraceEventKind` values this channel forwards, translated one-to-one —
#: the four the operator needs to know a list changed, out of the full set a
#: run's own trace records. Everything else — a tool call, a turn, a masked
#: argument — stays inside the run's own stream, which already serves it.
_RUN_KIND_TRANSLATION: Final[Mapping[TraceEventKind, DeploymentEventKind]] = {
    TraceEventKind.RUN_STARTED: DeploymentEventKind.RUN_STARTED,
    TraceEventKind.STAGE_COMPLETED: DeploymentEventKind.STAGE_COMPLETED,
    TraceEventKind.ATTENTION_CHANGED: DeploymentEventKind.ATTENTION_CHANGED,
    TraceEventKind.RUN_FINISHED: DeploymentEventKind.RUN_FINISHED,
}


def deployment_kind_of(event: RunEvent) -> DeploymentEventKind | None:
    """Return the deployment-channel kind ``event`` translates to, or ``None``.

    ``None`` for every `TraceEventKind` this channel does not carry — eleven of
    the fifteen declared today — which is the filter FR-003 names rather than a
    default this function invents.
    """
    return _RUN_KIND_TRANSLATION.get(event.kind)


@dataclass(slots=True)
class DeploymentPublishingRunEventBroker(RunEventBroker):
    """A `RunEventBroker` that also tells the deployment channel about four kinds.

    Composed once, at the gateway's root, in place of a plain `RunEventBroker` —
    every call site that already holds a `broker` and calls `.publish()` on it
    keeps doing exactly that, unaware that this object also forwards a filtered
    copy onward. No write call site changes; only what the root hands out as
    ``broker`` does.
    """

    deployment_events: DeploymentEventBroker | None = None

    async def publish(self, event: RunEvent) -> None:
        """Deliver ``event`` to this run's own subscribers, then tap it if it qualifies."""
        await super().publish(event)
        if self.deployment_events is None:
            return
        kind = deployment_kind_of(event)
        if kind is None:
            return
        await self.deployment_events.publish(
            scope=DeploymentScope.RUN, kind=kind, payload={"run_id": event.run_id}
        )


__all__ = [
    "DeploymentCursor",
    "DeploymentCursorError",
    "DeploymentEvent",
    "DeploymentEventBroker",
    "DeploymentEventKind",
    "DeploymentPublishingRunEventBroker",
    "DeploymentScope",
    "DeploymentSubscriberTooSlow",
    "deployment_kind_of",
]
