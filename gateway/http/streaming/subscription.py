"""Cursor handling and catch-up for one SSE connection (FR-010, SC-002).

A client's position is the ``Last-Event-ID`` header on reconnect, or nothing
for a first connection. ``platform.runs.stream.watching`` does the actual
catch-up-then-live read; this module turns that into the byte stream
``routes/investigations.py`` hands ``StreamingResponse``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from config.constants.surfaces import SSE_KEEPALIVE_INTERVAL_SECONDS
from gateway.http.errors import bad_request
from gateway.http.streaming.sse import HEARTBEAT_FRAME, sse_frame
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import RunTraceStore, TraceEventRecord
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.runs.cursor import Cursor, CursorError
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


__all__ = ["event_source", "parse_cursor"]
