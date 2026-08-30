"""Cursor handling and catch-up for one SSE connection (FR-010, SC-002).

A client's position is the ``Last-Event-ID`` header on reconnect, or nothing
for a first connection. ``platform.runs.stream.watching`` does the actual
catch-up-then-live read; this module turns that into the byte stream
``routes/investigations.py`` hands ``StreamingResponse``. The deployment
channel below shares the same shape — parse a cursor, then a generator that
yields SSE frames with heartbeats — over
``platform.runs.deployment.DeploymentEventBroker`` instead, which has no log
to catch up from and answers a gap it cannot cover with ``resync`` rather
than a replay.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from config.constants.runs import SSE_KEEPALIVE_SECONDS
from config.constants.surfaces import SSE_KEEPALIVE_INTERVAL_SECONDS
from gateway.http.errors import bad_request
from gateway.http.streaming.sse import HEARTBEAT_FRAME, deployment_sse_frame, sse_frame
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import RunTraceStore, TraceEventRecord
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.runs.cursor import Cursor, CursorError
from platform.runs.deployment import (
    DeploymentCursor,
    DeploymentCursorError,
    DeploymentEventBroker,
    DeploymentSubscriberTooSlow,
)
from platform.runs.stream import RunEventBroker, RunStream, SubscriberTooSlow, watching

logger = get_logger(__name__)


@dataclass(slots=True)
class _CatchUpStore:
    """The one ``RunTraceStore`` method a live stream's catch-up read calls.

    Opens a fresh, short-lived unit of work per read rather than holding one
    for the whole SSE connection's lifetime — which may be minutes — so a
    slow client never holds a database transaction open.
    """

    gateway: PersistenceGateway
    scope: TenantScope

    async def events_for_run(
        self, run_id: str, *, after: int | None = None, limit: int = 50
    ) -> tuple[TraceEventRecord, ...]:
        async with self.gateway.begin(self.scope) as uow:
            return await uow.run_traces.events_for_run(run_id, after=after, limit=limit)


def parse_cursor(run_id: str, last_event_id: str | None) -> Cursor:
    """Return the cursor a reconnecting client presents, or the start of the stream."""
    if not last_event_id:
        return Cursor.start_of(run_id)
    try:
        cursor = Cursor.parse(last_event_id)
    except CursorError as error:
        raise bad_request(f"Last-Event-ID is not a valid cursor: {error}") from error
    if cursor.run_id != run_id:
        raise bad_request("Last-Event-ID names a different run than the one being streamed")
    return cursor


#: How often a wait for the next event is interrupted to check whether the
#: client has gone — bounded well under the heartbeat interval, so a plain
#: disconnect (the client closed the connection, as opposed to a stalled one
#: that is still open) is noticed in about a second rather than at the next
#: heartbeat. A private cadence, not a bound Article II names: nothing about
#: the platform's behaviour changes if this number moves, only how quickly a
#: closed socket is noticed.
_DISCONNECT_POLL_SECONDS = 1.0


async def event_source(
    *,
    gateway: PersistenceGateway,
    scope: TenantScope,
    broker: RunEventBroker,
    run_id: str,
    cursor: Cursor,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    keepalive_seconds: float = SSE_KEEPALIVE_INTERVAL_SECONDS,
) -> AsyncIterator[bytes]:
    """Yield SSE frames: catch-up, then live, with heartbeats between events.

    A subscriber that falls behind the bounded buffer is disconnected here —
    ``SubscriberTooSlow`` ends the generator, which ends the HTTP response —
    without the run itself ever waiting on it (FR-012, SC-007). A subscriber
    that simply closed the connection is noticed via ``is_disconnected``,
    polled between short waits rather than only once per heartbeat.
    """
    stream = RunStream(
        store=cast(RunTraceStore, _CatchUpStore(gateway=gateway, scope=scope)), broker=broker
    )

    async with watching(stream, cursor) as events:
        waited = 0.0
        while True:
            if is_disconnected is not None and await is_disconnected():
                return
            slice_seconds = min(_DISCONNECT_POLL_SECONDS, keepalive_seconds - waited)
            try:
                event = await asyncio.wait_for(events.__anext__(), timeout=slice_seconds)
            except TimeoutError:
                waited += slice_seconds
                if waited >= keepalive_seconds:
                    yield HEARTBEAT_FRAME
                    waited = 0.0
                continue
            except StopAsyncIteration:
                return
            except SubscriberTooSlow:
                logger.warning("gateway.sse_subscriber_dropped", run_id=run_id)
                return
            waited = 0.0
            yield sse_frame(event)


def parse_deployment_cursor(last_event_id: str | None) -> DeploymentCursor | None:
    """Return the cursor a reconnecting client presents, or ``None`` for a first connection.

    ``None`` rather than a start-of-stream sentinel: a first connection to the
    deployment channel needs no catch-up at all, because the page that opened
    it already read its own current state (plan decision 1). Only a
    reconnection — one that presents ``Last-Event-ID`` — has a cursor to judge
    against the broker's memory.
    """
    if not last_event_id:
        return None
    try:
        return DeploymentCursor.parse(last_event_id)
    except DeploymentCursorError as error:
        raise bad_request(f"Last-Event-ID is not a valid cursor: {error}") from error


async def deployment_event_source(
    *,
    broker: DeploymentEventBroker,
    cursor: DeploymentCursor | None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    keepalive_seconds: float = SSE_KEEPALIVE_SECONDS,
) -> AsyncGenerator[bytes, None]:
    """Yield SSE frames: any backlog first, then live, with heartbeats between events.

    A subscriber that falls behind the bounded buffer is disconnected here —
    ``DeploymentSubscriberTooSlow`` ends the generator, which ends the HTTP
    response — without any write path that publishes to the broker ever
    waiting on it. A subscriber that simply closed the connection is noticed
    via ``is_disconnected``, polled between short waits rather than only once
    per heartbeat, the same way the per-run stream is.

    Polls ``subscription.drain()`` directly rather than wrapping
    ``follow_deployment_events`` in ``asyncio.wait_for`` the way the per-run
    ``event_source`` wraps ``RunStream.follow``: ``drain()`` never awaits
    anything itself, so there is nothing inside it for a timeout to cancel
    mid-flight. Doing it the other way once, here, showed the actual failure
    mode of that pattern — cancelling a coroutine that is suspended inside an
    async generator's own internal sleep does not just time out the call, it
    finalises the generator, and every subsequent ``__anext__()`` on it raises
    ``StopAsyncIteration`` instead of resuming. Wrapped in this function's own
    ``except StopAsyncIteration: return``, that ended the stream after exactly
    one heartbeat. Recorded here rather than silently worked around, because
    ``event_source`` for the per-run stream uses the same
    ``wait_for(generator.__anext__(), timeout=...)`` shape against
    ``RunStream.follow``, which polls on the same short interval — an idle run
    watched for a full keep-alive interval with nothing published is the
    condition this reproduces, and neither this module nor its tests are the
    place to change that call, which this feature's file scope does not reach.
    """
    subscription, backlog = broker.attach(cursor)
    try:
        for event in backlog:
            yield deployment_sse_frame(event, epoch=broker.epoch)

        waited = 0.0
        while True:
            if is_disconnected is not None and await is_disconnected():
                return
            try:
                delivered = False
                async for event in subscription.drain():
                    delivered = True
                    waited = 0.0
                    yield deployment_sse_frame(event, epoch=broker.epoch)
            except DeploymentSubscriberTooSlow:
                logger.warning("gateway.deployment_sse_subscriber_dropped")
                return
            if delivered:
                continue

            slice_seconds = min(_DISCONNECT_POLL_SECONDS, keepalive_seconds - waited)
            await asyncio.sleep(max(slice_seconds, 0.0))
            waited += slice_seconds
            if waited >= keepalive_seconds:
                yield HEARTBEAT_FRAME
                waited = 0.0
    finally:
        broker.detach(subscription)


__all__ = [
    "deployment_event_source",
    "event_source",
    "parse_cursor",
    "parse_deployment_cursor",
]
