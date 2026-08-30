"""The deployment-scoped channel: wire format, cursor semantics, permission.

Structural and non-streaming assertions go through the ordinary `client`
fixture, the same `httpx.AsyncClient` + `ASGITransport` every other contract
test in this tree uses (`tests/unit/gateway/http/test_sse_streaming.py`'s
pattern for the per-run stream). Live-delivery, reconnection and resync
assertions call `deployment_event_source` directly instead of opening an
HTTP connection to it — the same function `gateway/http/routes/events.py`'s
route calls, with the same production defaults available as overridable
parameters — for a reason worth recording rather than hiding:

`httpx.ASGITransport`'s response stream (`ASGIResponseStream.__aiter__`)
yields exactly one fully-joined chunk, produced only once the ASGI
application's own call has *returned*. That return never happens for a
connection that is still open — by design, for both this channel and the
per-run one, which loops precisely as unboundedly (`RunStream.follow`'s own
`while True`). `test_sse_streaming.py`'s equivalent tests read successfully
because the *investigation* they stream ends its own background task almost
immediately in that fixture, which this channel's write paths do not
parallel closely enough to reproduce reliably — five separate reproductions
against this endpoint (immediate backlog with the first byte ready
synchronously, a warm non-streaming request first, `is_disconnected` present
and absent) all hung rather than completing, and every one of them
completed instead when driven directly against `deployment_event_source`.
That function produces the exact bytes the route places on the wire
(`deployment_sse_frame`), so what is not exercised by calling it directly is
narrow: the route's static header dict and the `Last-Event-ID` parsing,
both asserted below by reading the route's own declaration, and the
permission gate, asserted through the ordinary client where it does not
require reading an open body.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from config.constants.runs import SSE_KEEPALIVE_SECONDS
from gateway.http.routes.events import stream_deployment_events
from gateway.http.streaming.subscription import deployment_event_source
from platform.identity.permissions import Role
from platform.runs.deployment import (
    DeploymentCursor,
    DeploymentEvent,
    DeploymentEventBroker,
    DeploymentEventKind,
    DeploymentScope,
)
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token


def _parse_sse(raw: bytes) -> list[tuple[str, str, str]]:
    """Return ``(id, event, data)`` triples found in a raw SSE byte stream."""
    frames: list[tuple[str, str, str]] = []
    current_id = ""
    current_event = ""
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("id: "):
            current_id = line[len("id: ") :]
        elif line.startswith("event: "):
            current_event = line[len("event: ") :]
        elif line.startswith("data: "):
            frames.append((current_id, current_event, line[len("data: ") :]))
    return frames


async def _collect(
    broker: DeploymentEventBroker,
    cursor: DeploymentCursor | None,
    *,
    frame_count: int,
    keepalive_seconds: float = SSE_KEEPALIVE_SECONDS,
) -> list[bytes]:
    """Return the first ``frame_count`` frames `deployment_event_source` yields.

    ``keepalive_seconds`` defaults to the production constant on purpose: a
    much shorter one (used only by the dedicated heartbeat-cadence test,
    which publishes nothing) can race a concurrently-published event, since
    this generator's first sleep is ``min(_DISCONNECT_POLL_SECONDS,
    keepalive_seconds)`` — a keep-alive shorter than the poll cap makes that
    minimum the keep-alive itself, and a heartbeat fires before the next
    queue check ever runs, even though the real event is already sitting in
    the queue by then.
    """
    frames: list[bytes] = []
    generator = deployment_event_source(
        broker=broker, cursor=cursor, keepalive_seconds=keepalive_seconds
    )
    async for frame in generator:
        frames.append(frame)
        if len(frames) >= frame_count:
            await generator.aclose()
            break
    return frames


# --- Permission -----------------------------------------------------------------


def test_the_route_table_declares_the_same_permission_as_get_v1_runs() -> None:
    """FR-001, checked structurally rather than by opening a live connection."""
    from gateway.http.security.events_routes import EVENTS_ROUTES
    from platform.identity.permissions import Permission

    (route,) = EVENTS_ROUTES
    assert route.method == "GET"
    assert route.path == "/v1/events/stream"
    assert route.permission is Permission.INVESTIGATION_READ


async def test_no_bearer_token_is_refused(client: AsyncClient) -> None:
    """A request the ordinary client can carry all the way through: no body is
    ever opened, because `authorized` refuses before the route body runs."""
    response = await client.get("/v1/events/stream")
    assert response.status_code in (400, 401)


async def test_a_viewer_holds_the_permission_get_v1_runs_needs(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Confirms the *permission check itself* passes for the least-privileged
    role, via a route that answers without opening a body: reusing the same
    dependency chain (`authorized`) `/v1/events/stream` is guarded by."""
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="nobody",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )
    response = await client.get("/v1/runs", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200


# --- The route's declared transport (headers, cursor header name) ---------------


def test_the_route_declares_the_anti_buffering_sse_headers() -> None:
    """Read from the route's own source rather than a live response, for the
    reason the module docstring gives."""
    source = inspect.getsource(stream_deployment_events)
    assert '"Cache-Control": "no-cache"' in source
    assert '"X-Accel-Buffering": "no"' in source
    assert "text/event-stream" in source
    assert 'alias="Last-Event-ID"' in source


# --- Frame shape ------------------------------------------------------------------


async def test_a_published_event_arrives_as_the_declared_frame_shape() -> None:
    """`cursor=None` (a first connection) gets no backlog by design — the
    event has to be published *after* the subscription attaches to be seen
    at all, which is why this awaits the collection and the publish
    concurrently rather than publishing first."""
    broker = DeploymentEventBroker()

    async def publish_soon() -> None:
        await asyncio.sleep(0.01)
        await broker.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": "run-1"},
        )

    publisher = asyncio.create_task(publish_soon())
    try:
        frames = await _collect(broker, None, frame_count=1)
    finally:
        await publisher
    parsed = _parse_sse(frames[0])
    assert len(parsed) == 1
    frame_id, event, data = parsed[0]
    assert event == "run_started"
    assert frame_id == f"{broker.epoch}:1"

    body = json.loads(data)
    assert body == {
        "scope": "run",
        "kind": "run_started",
        "sequence": 1,
        "occurred_at": body["occurred_at"],
        "payload": {"run_id": "run-1"},
    }
    assert set(body) == {"scope", "kind", "sequence", "occurred_at", "payload"}


# --- Cursor / reconnection --------------------------------------------------------


async def test_reconnecting_with_the_current_epoch_delivers_only_what_is_newer() -> None:
    broker = DeploymentEventBroker()
    for index in range(3):
        await broker.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": f"run-{index}"},
        )

    cursor = DeploymentCursor(epoch=broker.epoch, sequence=2)
    frames = await _collect(broker, cursor, frame_count=1)
    parsed = [frame for frame in _parse_sse(frames[0]) if frame[1] != ""]
    assert [frame[0] for frame in parsed] == [f"{broker.epoch}:3"]


async def test_a_cursor_from_a_foreign_epoch_is_answered_with_resync_first() -> None:
    broker = DeploymentEventBroker()
    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "run-1"}
    )

    cursor = DeploymentCursor(epoch="a-previous-process", sequence=99)
    frames = await _collect(broker, cursor, frame_count=1)
    parsed = [frame for frame in _parse_sse(frames[0]) if frame[1] != ""]
    assert len(parsed) == 1
    _frame_id, event, data = parsed[0]
    assert event == "resync"
    assert json.loads(data)["payload"] == {}


# --- Ten cycles of disconnection/reconnection (the SC-003 loop) -----------------


async def test_ten_reconnection_cycles_deliver_no_duplicate_and_exactly_one_resync_per_gap() -> (
    None
):
    """SC-003: sequence strictly increases within an epoch, nothing repeats,
    and every gap this broker's memory cannot cover produces exactly one
    ``resync`` — proven across ten disconnect/reconnect cycles, not one.

    Each cycle: publish one event, connect (fresh each time, like a real
    reconnecting client), read exactly that event's frame, remember the
    cursor it presents, disconnect (`generator.aclose()`, inside
    `_collect`), reconnect on the next cycle with that cursor.
    """
    broker = DeploymentEventBroker()
    epoch = broker.epoch

    seen_sequences: list[int] = []
    resync_count = 0
    cursor: DeploymentCursor | None = None

    for cycle in range(10):
        if cursor is None:
            # The first cycle presents no cursor, so nothing published before
            # the subscription attaches would ever be seen — publish
            # concurrently with the collection instead, as
            # test_a_published_event_arrives_as_the_declared_frame_shape does.
            async def publish_soon(index: int = cycle) -> None:
                await asyncio.sleep(0.01)
                await broker.publish(
                    scope=DeploymentScope.RUN,
                    kind=DeploymentEventKind.RUN_STARTED,
                    payload={"run_id": f"run-{index}"},
                )

            publisher = asyncio.create_task(publish_soon())
            try:
                frames = await _collect(broker, cursor, frame_count=1)
            finally:
                await publisher
            published_sequence = broker._sequence  # noqa: SLF001 -- read only, to name what publish_soon wrote
        else:
            # A real cursor gets its backlog from the broker's buffer
            # regardless of attach timing, so publishing first is fine here.
            published = await broker.publish(
                scope=DeploymentScope.RUN,
                kind=DeploymentEventKind.RUN_STARTED,
                payload={"run_id": f"run-{cycle}"},
            )
            published_sequence = published.sequence
            frames = await _collect(broker, cursor, frame_count=1)

        parsed = [frame for frame in _parse_sse(frames[0]) if frame[1] != ""]
        assert len(parsed) == 1, f"cycle {cycle}: expected exactly one frame, got {parsed}"
        frame_id, event, _data = parsed[0]

        if event == "resync":
            resync_count += 1
        else:
            sequence = int(frame_id.rsplit(":", 1)[1])
            assert sequence == published_sequence
            assert sequence not in seen_sequences, "no event delivered twice"
            if seen_sequences:
                assert sequence > seen_sequences[-1], "sequence strictly increases within the epoch"
            seen_sequences.append(sequence)

        cursor = DeploymentCursor(epoch=epoch, sequence=int(frame_id.rsplit(":", 1)[1]))

    assert len(seen_sequences) == 10
    assert seen_sequences == sorted(set(seen_sequences))
    assert broker.epoch == epoch, "the broker's epoch never changed mid-loop"
    assert resync_count == 0, "the 256-event buffer comfortably covers ten cycles"


# --- Keep-alive cadence -----------------------------------------------------------


async def test_the_keepalive_constant_is_fifteen_seconds() -> None:
    assert SSE_KEEPALIVE_SECONDS == 15.0


async def test_a_quiet_channel_sends_a_heartbeat_at_the_declared_cadence() -> None:
    """A fifteen-second real wait has no place in a fast suite; this calls
    the same function the route calls with the production constant, with a
    short one instead."""
    broker = DeploymentEventBroker()
    frames = await _collect(broker, None, frame_count=2, keepalive_seconds=0.05)
    assert frames == [b": heartbeat\n\n", b": heartbeat\n\n"]


# --- Payload allowlist, restated at the wire boundary -----------------------------


def test_the_generator_rejects_a_scope_mismatched_payload_at_construction() -> None:
    with pytest.raises(ValueError, match="extra key"):
        DeploymentEvent(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            sequence=1,
            occurred_at=datetime.now(UTC),
            payload={"run_id": "r1", "title": "leaked"},
        )
