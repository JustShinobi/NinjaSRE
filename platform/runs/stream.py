"""Watching a run that is happening, and catching up on one you stopped watching.

The design is one sentence: **the event log is the source of truth and the
pub/sub is a delivery optimisation.** Everything else here follows from it.

A subscriber that arrives with a cursor is served from the log until the log has
nothing newer, and only then attached to the broker. Attaching first and
back-filling afterwards would need the two streams merged and de-duplicated by
the client, which is the design in which "exactly once" becomes "usually once".
Attaching *while* reading the log is what this module actually does — the
subscription is registered before the catch-up read, and events arriving during
it are buffered and filtered by cursor as they are drained. A subscriber
registered after the read would miss anything published in between.

A slow subscriber is dropped rather than buffered without bound. That sounds
harsh and is the kindest option available: a client that falls behind holds its
cursor, reconnects, and misses nothing, because the log still has everything.
The alternative — an unbounded queue — is a memory leak with a client attached,
and it fails the whole process rather than one reader.

Across replicas, the recording process is not necessarily the one a client is
connected to. ``StreamBridge`` is the seam a Postgres ``LISTEN``/``NOTIFY``
fan-out — or any other — would be written against, and **nothing in this
repository implements it**: the port is declared, ``bridge`` defaults to
``None``, and the serving composition root supplies none. So a deployment runs
one application replica until something does implement it, and the chart says
so where it sets the replica count. A single-process deployment works
completely with no bridge, which is why the seam is optional rather than
required — but "optional" is not "configured", and an operator told to wire a
bridge would be looking for a class that does not exist.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from config.constants.runs import MAX_STREAM_BUFFER_EVENTS, STREAM_CATCH_UP_PAGE_SIZE
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import RunTraceStore
from platform.runs.cursor import Cursor
from platform.runs.events import RunEvent

logger = get_logger(__name__)


class SubscriberTooSlow(RuntimeError):
    """A subscriber fell further behind than the buffer allows.

    Recoverable by construction: the client reconnects with the cursor it last
    acknowledged and reads the backlog from the log. That is what makes dropping
    it the right answer rather than a failure to deliver.
    """

    def __init__(self, run_id: str, *, buffered: int) -> None:
        super().__init__(
            f"A subscriber to {run_id} fell {buffered} events behind, past the "
            f"{MAX_STREAM_BUFFER_EVENTS}-event buffer. Reconnect with the last "
            "cursor it acknowledged; the log still holds everything it missed."
        )
        self.run_id = run_id
        self.buffered = buffered


@runtime_checkable
class StreamBridge(Protocol):
    """Carries events between the replicas of one deployment.

    Two methods, and neither of them is "store": the log already did that. A
    bridge only has to get an event that one replica recorded to the brokers on
    the others, and it may drop one — the client's cursor and the log are what
    make that survivable.

    Nothing implements this today; see the module docstring for what that costs
    a deployment.
    """

    async def publish(self, event: RunEvent, *, org_id: str) -> None:
        """Send ``event``, and the organisation whose run it is, to the other replicas.

        The tenant travels beside the event rather than on it because a
        `RunEvent` is a row of one run's log and the log stores no organisation
        — the store it came out of was already opened for one. A bridge that
        dropped the tenant would leave the receiving replica holding an event it
        could only treat as everybody's.
        """

    def subscribe(self, deliver: Callable[[RunEvent], None]) -> None:
        """Register ``deliver`` to be called with events from other replicas."""


@dataclass(slots=True)
class Subscription:
    """One client's attachment to one run.

    Holds a bounded queue and the cursor of the last event handed over. The
    cursor is what makes the same subscription resumable after the queue
    overflows, and it advances only when an event is actually yielded — not when
    one is enqueued — so a client that died mid-iteration resumes from what it
    read rather than from what was sent.
    """

    run_id: str
    cursor: Cursor
    _queue: asyncio.Queue[RunEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_STREAM_BUFFER_EVENTS)
    )
    _overflowed: bool = False
    _closed: bool = False

    def offer(self, event: RunEvent) -> None:
        """Enqueue ``event`` for this subscriber, or mark it as fallen behind.

        Never blocks. A publisher awaiting a slow reader would make one client's
        pace the whole run's pace, and the run is doing incident response.
        """
        if self._closed or self._overflowed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._overflowed = True
            logger.warning(
                "runs.subscriber_dropped",
                run_id=self.run_id,
                buffered=self._queue.qsize(),
                cursor=str(self.cursor),
            )

    def close(self) -> None:
        """Stop delivering to this subscriber."""
        self._closed = True

    @property
    def overflowed(self) -> bool:
        """Return whether this subscriber fell past the buffer."""
        return self._overflowed

    async def drain(self) -> AsyncIterator[RunEvent]:
        """Yield buffered events in order, advancing the cursor as they go.

        Events at or before the cursor are dropped rather than yielded. That is
        the de-duplication that makes a catch-up read and a live attachment
        composable: the overlap between them is exactly the events the client
        already has.
        """
        while not self._queue.empty():
            if self._overflowed:
                raise SubscriberTooSlow(self.run_id, buffered=self._queue.qsize())
            event = self._queue.get_nowait()
            if event.sequence <= self.cursor.position:
                continue
            self.cursor = self.cursor.advanced_to(event.sequence)
            yield event


@dataclass(slots=True)
class RunEventBroker:
    """In-process fan-out from the recorder to whoever is watching.

    Deliberately not durable and deliberately not ordered against the log: it
    delivers what it is given, to whoever is attached, and anything it loses is
    recoverable from the log by cursor. A broker that tried to guarantee more
    would be a second event log, kept in step with the first by hand.
    """

    bridge: StreamBridge | None = None
    _subscribers: dict[str, list[Subscription]] = field(default_factory=dict)
    _bridged: bool = False

    def attach(self, run_id: str, *, cursor: Cursor | None = None) -> Subscription:
        """Register and return a subscription to ``run_id``."""
        subscription = Subscription(run_id=run_id, cursor=cursor or Cursor.start_of(run_id))
        self._subscribers.setdefault(run_id, []).append(subscription)
        self._ensure_bridged()
        return subscription

    def detach(self, subscription: Subscription) -> None:
        """Remove ``subscription`` and stop delivering to it."""
        subscription.close()
        held = self._subscribers.get(subscription.run_id)
        if held is None:
            return
        self._subscribers[subscription.run_id] = [s for s in held if s is not subscription]
        if not self._subscribers[subscription.run_id]:
            del self._subscribers[subscription.run_id]

    def subscribers(self, run_id: str) -> int:
        """Return how many clients are watching ``run_id``."""
        return len(self._subscribers.get(run_id, ()))

    async def publish(self, event: RunEvent, *, org_id: str) -> None:
        """Deliver ``event`` locally and hand it and its tenant to the bridge.

        Locally first. A bridge that is slow or down must not delay the clients
        attached to the replica that recorded the event, which are the ones most
        likely to be the operator watching it happen.

        ``org_id`` names whose run this is, and is required with no default.
        This broker's own fan-out does not consult it — it keys on the run id,
        and a subscriber only ever holds a run it was authorised to watch — but
        one broker serves every organisation in the process, and
        `platform.runs.deployment.DeploymentPublishingRunEventBroker` forwards a
        filtered copy of four kinds onto the deployment-wide channel, where the
        tenant is the whole of what decides who a frame reaches. A default here
        would be the value a call site that never thought about tenancy takes,
        and that value can only be "everyone".
        """
        self.deliver(event)
        if self.bridge is not None:
            await self.bridge.publish(event, org_id=org_id)

    def deliver(self, event: RunEvent) -> None:
        """Deliver ``event`` to this replica's subscribers only.

        What the bridge calls on the receiving side, and what ``publish`` calls
        before handing over. Separating them is what stops a bridged event being
        sent straight back across the bridge.

        No tenant, and none needed: this is the per-run fan-out, and a
        subscription exists only because a client asked to watch a run it was
        authorised for. The deployment-wide forward, which is where the tenant
        decides anything, hangs off ``publish`` alone.
        """
        for subscription in self._subscribers.get(event.run_id, ()):
            subscription.offer(event)

    def _ensure_bridged(self) -> None:
        """Register with the bridge once, on the first subscription.

        Lazily, because a deployment with a bridge configured and nobody
        watching should not be receiving every event every other replica
        records.
        """
        if self._bridged or self.bridge is None:
            return
        self.bridge.subscribe(self.deliver)
        self._bridged = True


@dataclass(frozen=True, slots=True)
class RunEventPublisher:
    """A run broker, paired with the organisation whose runs go into it.

    The broker is built once per process and carries every organisation's runs;
    the tenant is not on the event and cannot be, because a `RunEvent` is a row
    of one run's log and the log stores no organisation. Pairing the two here is
    what makes an unattributed publish unspellable rather than merely
    discouraged: `platform.runs.recorder.RunRecorder` cannot be given somewhere
    to publish without also being told whose runs it is publishing, so a call
    site that never considered tenancy fails to type check instead of reaching
    every subscriber in the deployment.

    ``org_id`` is the organisation the recorder's unit of work was opened for.
    Every construction site has it in hand — a recorder holds a store that came
    out of a scoped unit, and the scope is the line above.
    """

    broker: RunEventBroker
    org_id: str

    async def publish(self, event: RunEvent) -> None:
        """Publish ``event`` on the broker, attributed to this organisation."""
        await self.broker.publish(event, org_id=self.org_id)


@dataclass(slots=True)
class RunStream:
    """The catch-up-then-live read a client actually performs.

    Holds the store as well as the broker because catching up is a read of the
    log, and a stream that could only deliver live events would be one that
    silently began wherever the client happened to connect.
    """

    store: RunTraceStore
    broker: RunEventBroker

    async def replay_from(self, cursor: Cursor) -> tuple[RunEvent, ...]:
        """Return everything logged after ``cursor``, in order.

        Bounded per read. A client reconnecting to a long-running investigation
        streams its backlog rather than materialising the whole of it, and a
        caller wanting more calls again with the cursor it reached.
        """
        records = await self.store.events_for_run(
            cursor.run_id, after=cursor.after, limit=STREAM_CATCH_UP_PAGE_SIZE
        )
        return tuple(RunEvent.of(record) for record in records)

    async def follow(self, cursor: Cursor) -> AsyncGenerator[RunEvent]:
        """Yield everything after ``cursor``, from the log and then live.

        The subscription is registered *before* the catch-up read, so an event
        recorded during the read is buffered rather than lost. The overlap that
        creates — an event both read from the log and buffered by the broker —
        is removed by the subscription's own cursor, which is why de-duplication
        lives there and not here.
        """
        subscription = self.broker.attach(cursor.run_id, cursor=cursor)
        try:
            position = cursor
            while True:
                caught_up = await self.replay_from(position)
                if not caught_up:
                    break
                for event in caught_up:
                    position = position.advanced_to(event.sequence)
                    subscription.cursor = position
                    yield event

            while True:
                async for event in subscription.drain():
                    yield event
                await asyncio.sleep(0)
                if subscription.overflowed:
                    raise SubscriberTooSlow(cursor.run_id, buffered=MAX_STREAM_BUFFER_EVENTS)
                # Yielding control is what lets a caller stop iterating; the
                # generator is closed at that point and the ``finally`` detaches.
                await asyncio.sleep(_POLL_SECONDS)
        finally:
            self.broker.detach(subscription)

    async def snapshot(self, run_id: str) -> tuple[RunEvent, ...]:
        """Return the whole log of ``run_id``, for a client that wants it at once."""
        records = await self.store.events_for_run(run_id, limit=MAX_QUERY_PAGE_SIZE)
        return tuple(RunEvent.of(record) for record in records)


#: How long ``follow`` waits between drains when nothing is arriving. Short
#: enough that an operator watching a live run sees it as live, long enough that
#: an idle subscriber is not a busy loop.
_POLL_SECONDS = 0.05


@contextlib.asynccontextmanager
async def watching(stream: RunStream, cursor: Cursor) -> AsyncIterator[AsyncGenerator[RunEvent]]:
    """Yield ``stream.follow(cursor)``, closing the generator on exit.

    An async generator abandoned without being closed leaves its subscription
    attached until the garbage collector gets to it, and the broker would go on
    filling a queue nobody reads. Typed as ``AsyncGenerator`` rather than
    ``AsyncIterator`` precisely so ``aclose`` is part of what a caller is
    handed: an iterator that cannot be closed is one this helper cannot help
    with.
    """
    events = stream.follow(cursor)
    try:
        yield events
    finally:
        await events.aclose()


__all__ = [
    "RunEventBroker",
    "RunEventPublisher",
    "RunStream",
    "StreamBridge",
    "SubscriberTooSlow",
    "Subscription",
    "watching",
]
