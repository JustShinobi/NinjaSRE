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

**One broker, one tenant at a time.** The broker is process-wide, and a
deployment serves more than one organisation — a token resolves to whichever
organisation its own row names, and a second one is created by a shipped path.
So every event carries the organisation it belongs to on its *envelope*, every
subscriber names the organisation it may hear about, and both the live path and
the backlog replay deliver only what matches. Not on the payload: ``org_id`` is
deliberately absent from ``_ALLOWED_PAYLOAD_KEYS`` below, so it decides who a
frame reaches and is never serialised to a client — a reader's own organisation
is the only one they can ever be sent, which makes telling them redundant, and
a field that never crosses the wire cannot be read off it.

Every publisher onto this channel names an organisation today, run-scope events
included — see ``DeploymentPublishingRunEventBroker.publish`` at the foot of
this module, which forwards the tenant its caller was required to name. The
envelope still admits ``None``, meaning "not attributable to one organisation",
and an event carrying it reaches every subscriber; nothing publishes one, and a
publisher that wants to has to pass it explicitly and mean it.
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
    """The eleven kinds of frame this channel ever carries, and no others.

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
    #: Withdrawn without an answer — the one way a proposal leaves the queue
    #: that is nobody's decision about it. Its own kind rather than a second
    #: meaning for `decision_decided`, because a reader counting what a person
    #: said about a proposal and a reader counting what is still waiting are
    #: asking different questions, and only one of them should count this.
    DECISION_DISCARDED = "decision_discarded"
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
            DeploymentEventKind.DECISION_DISCARDED,
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
    #: Which organisation's fact this is — the envelope, deliberately not a
    #: payload key. Kept off `_ALLOWED_PAYLOAD_KEYS` so it cannot be
    #: serialised by accident: `gateway.http.streaming.sse.deployment_sse_frame`
    #: builds a client's frame out of the scope, the kind, the sequence, the
    #: instant and the payload, and this is none of them. It exists to decide
    #: who a frame is delivered to, and a reader has no use for it — the org
    #: they are in is the only one they can ever be sent.
    #:
    #: ``None`` means "not attributable to one organisation", and such an event
    #: reaches every subscriber. Nothing publishes one today: every tap names a
    #: tenant, and a ``resync`` is minted with the organisation of the
    #: connection that provoked it.
    org_id: str | None = None

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
    """One client's live attachment to the deployment channel, within one tenant.

    ``org_id`` is the organisation the connection's own token resolved to, and
    it is the whole of what this subscriber may ever hear about. Required, with
    no default: an attachment that forgot to name a tenant would be one that
    hears every tenant, which is the failure this field exists to make
    unspellable rather than merely discouraged.
    """

    org_id: str
    _queue: asyncio.Queue[DeploymentEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEPLOYMENT_STREAM_BUFFER_EVENTS)
    )
    _overflowed: bool = False
    _closed: bool = False

    def wants(self, event: DeploymentEvent) -> bool:
        """Return whether ``event`` is this subscriber's to see.

        An event attributed to another organisation is not — its ids, its kind
        and its timing are all facts about a deployment this caller has no
        route to read. An unattributed event (``org_id is None``) is, and no
        publisher mints one: every tap names the tenant its unit of work was
        opened for, every run event names the one its recorder was built with,
        and a ``resync`` is minted with the organisation of the connection that
        provoked it. The permissive reading is kept for a frame constructed
        directly rather than published — a test's, or a control frame a later
        connection-scoped kind might need — and it is safe there precisely
        because it cannot be reached by forgetting: ``publish`` takes the
        organisation as a keyword with no default.
        """
        return event.org_id is None or event.org_id == self.org_id

    def offer(self, event: DeploymentEvent) -> None:
        """Enqueue ``event`` if it is this subscriber's, or mark it fallen behind.

        Never blocks, and filters before it enqueues rather than after: an
        event this client may not see must not occupy a slot in its bounded
        buffer, or one busy tenant would push another's client into ``resync``.
        """
        if self._closed or self._overflowed or not self.wants(event):
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
        self,
        *,
        scope: DeploymentScope,
        kind: DeploymentEventKind,
        payload: Mapping[str, Any],
        org_id: str | None,
    ) -> DeploymentEvent:
        """Assign the next sequence to one fact, remember it, and deliver it live.

        ``org_id`` names whose fact this is, and is required rather than
        defaulted: a publisher that cannot say has to say so, by passing
        ``None`` and meaning it, because the default a busy call site would
        have taken is the one that reaches every tenant.

        Delivery never waits on a subscriber: `_Subscription.offer` does not
        block, so one slow reader cannot make this call — which every write
        path this feature taps runs on — wait on it.
        """
        self._sequence += 1
        event = DeploymentEvent(
            scope=scope,
            kind=kind,
            sequence=self._sequence,
            occurred_at=_utc_now(),
            payload=payload,
            org_id=org_id,
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
        self, cursor: DeploymentCursor | None = None, *, org_id: str
    ) -> tuple[_Subscription, tuple[DeploymentEvent, ...]]:
        """Register a live subscriber for ``org_id`` and return what it should see first.

        A first connection (``cursor`` is ``None``) needs nothing backfilled: the
        page that opened the channel already read its own current state. A
        reconnection this broker's memory can cover is backfilled from the
        buffer. A reconnection it cannot cover — a different epoch, or a
        position older than the buffer's oldest entry — gets exactly one
        `resync` event instead, at the current tip, so the client refreshes once
        and then watches forward from here rather than from a hole this memory
        cannot honestly fill.

        The backlog is filtered by ``org_id`` exactly as the live path is. The
        buffer is one deque for the whole process, so replaying it unfiltered
        would hand a reconnecting client everything every other tenant did
        while it was away — the same leak as the live path, reached by pressing
        reload.

        ``org_id`` is the caller's own, taken from the token their connection
        authenticated with. This method has no way to check that and does not
        try: the route above it (`gateway.http.routes.events`) reads it from
        ``auth.scope``, which is the authenticated token's own tenant and never
        a value a request named.
        """
        subscription = _Subscription(org_id=org_id)
        self._subscribers.append(subscription)

        if cursor is None:
            return subscription, ()

        if cursor.epoch == self.epoch and self._coverable(cursor.sequence):
            backlog = tuple(
                event
                for event in self._buffer
                if event.sequence > cursor.sequence and subscription.wants(event)
            )
            return subscription, backlog

        resync = DeploymentEvent(
            scope=DeploymentScope.CONTROL,
            kind=DeploymentEventKind.RESYNC,
            sequence=self._sequence,
            occurred_at=_utc_now(),
            payload={},
            org_id=org_id,
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

    async def publish(self, event: RunEvent, *, org_id: str) -> None:
        """Deliver ``event`` to this run's own subscribers, then tap it if it qualifies."""
        await super().publish(event, org_id=org_id)
        if self.deployment_events is None:
            return
        kind = deployment_kind_of(event)
        if kind is None:
            return
        # The organisation the publisher named, carried straight onto the
        # envelope. It arrives beside the event rather than on it because a
        # `RunEvent` is a row of one run's log and the log stores no tenant —
        # the store it came out of was already opened for one. What makes this
        # trustworthy is that `platform.runs.stream.RunEventPublisher` is the
        # only way a `RunRecorder` is given somewhere to publish, and it cannot
        # be built without an organisation.
        await self.deployment_events.publish(
            scope=DeploymentScope.RUN, kind=kind, payload={"run_id": event.run_id}, org_id=org_id
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
