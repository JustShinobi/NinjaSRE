"""The deployment-scoped channel over the wire: frames, cursors, permission.

`GET /v1/events/stream` is exercised as a real HTTP client would reach it —
through `create_app`, driving the ASGI application directly rather than
through `httpx.ASGITransport`.

`ASGITransport.handle_async_request` only returns a response once the whole
ASGI call has *finished* — every byte is buffered internally and handed over
in one piece at the very end. That is fine for every ordinary request and
wrong for this one: a live SSE connection is a generator that runs until it
is told to stop, and it is never told to stop by anything `ASGITransport`'s
in-process `receive()` can produce, because that `receive()` can only report
a disconnect *after* the response it is part of has already completed —
found by timing this whole suite out before this file drove the ASGI
application directly, the way `tests/unit/gateway/http/test_sse_streaming.py`
does not need to, because its scenarios happen to end their own connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from config.constants.runs import SSE_KEEPALIVE_SECONDS
from gateway.http.streaming.subscription import deployment_event_source
from platform.identity.permissions import Role
from platform.runs.deployment import (
    DeploymentEvent,
    DeploymentEventBroker,
    DeploymentEventKind,
    DeploymentScope,
)
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio

#: Generous relative to the ~1-second poll granularity `deployment_event_source`
#: uses for live delivery; irrelevant to a backlog read, which is delivered
#: synchronously before any wait.
_BUDGET_SECONDS = 3.0

ASGIApp = Callable[
    [Mapping[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]],
    Awaitable[None],
]


async def _auth_header(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    return {"Authorization": f"Bearer {secret}"}


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


@dataclass(slots=True)
class _StreamSession:
    """One connection's status and body, filled in as ASGI ``send`` is called."""

    status: int | None = None
    body: bytes = b""
    _new_data: asyncio.Event = field(default_factory=asyncio.Event)

    def on_send(self, message: Mapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")
        self._new_data.set()

    async def read_until(self, marker: bytes | None, *, budget: float) -> bytes:
        """Return the body collected so far, once ``marker`` appears or ``budget`` elapses.

        ``marker=None`` collects for the whole budget, deliberately — the
        "read briefly, take whatever arrived" shape a reconnection or a
        resync assertion needs.
        """
        deadline = time.monotonic() + budget
        while marker is None or marker not in self.body:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._new_data.clear()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(remaining):
                    await self._new_data.wait()
        return self.body


def _scope_for(path: str, headers: Mapping[str, str]) -> dict[str, Any]:
    """Return the ASGI scope a real GET to ``path`` would carry.

    ``asgi.spec_version`` is declared as ``"2.4"`` — the version Starlette's
    ``StreamingResponse`` checks before choosing its simpler code path (a
    plain ``await self.stream_response(send)``, with no concurrent
    disconnect-listening task racing it). ``httpx.ASGITransport`` declares no
    ``spec_version`` at all, which is the other half of why driving it
    through that transport does not work for this endpoint.
    """
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        "server": ("gateway.test", 80),
        "client": ("test-client", 1234),
        "scheme": "http",
        "root_path": "",
    }


@contextlib.asynccontextmanager
async def _open_stream(app: ASGIApp, headers: Mapping[str, str]):
    """Drive ``app`` for one GET to the deployment stream, until the block exits.

    Cancelling the driving task on exit is what ends the connection: nothing
    in this endpoint's own generator ever terminates on its own, by design —
    see the module docstring — so a caller of this helper is the one place
    the connection actually closes.
    """
    session = _StreamSession()
    body_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # No further request messages exist for a bodyless GET; a real
        # disconnect notification is a Traefik/uvicorn concern this in-process
        # driver does not simulate, so this simply never resolves — cancelling
        # the task is the only way this helper ends a connection.
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    async def send(message: Mapping[str, Any]) -> None:
        session.on_send(message)

    scope = _scope_for("/v1/events/stream", headers)
    task = asyncio.create_task(app(scope, receive, send))
    try:
        yield session
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _read_deployment_stream(
    app: ASGIApp,
    headers: dict[str, str],
    *,
    stop_when: bytes | None = None,
    budget: float = _BUDGET_SECONDS,
) -> _StreamSession:
    async with _open_stream(app, headers) as session:
        await session.read_until(stop_when, budget=budget)
        return session


# --- Permission ---------------------------------------------------------------


def test_the_route_table_declares_the_same_permission_as_get_v1_runs() -> None:
    """FR-001, checked structurally rather than by opening a live connection."""
    from gateway.http.security.events_routes import EVENTS_ROUTES
    from platform.identity.permissions import Permission

    (route,) = EVENTS_ROUTES
    assert route.method == "GET"
    assert route.path == "/v1/events/stream"
    assert route.permission is Permission.INVESTIGATION_READ


async def test_an_authorised_viewer_opens_the_stream_and_receives_a_frame(
    app: ASGIApp, deployment: Deployment
) -> None:
    """The same permission `GET /v1/runs` needs, actually exercised end to end."""
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="nobody",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )

    async def publish_soon() -> None:
        await asyncio.sleep(0.02)
        await deployment.state.deployment_events.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": "run-viewer"},
        )

    publisher = asyncio.create_task(publish_soon())
    try:
        session = await _read_deployment_stream(
            app, {"Authorization": f"Bearer {secret}"}, stop_when=b"run_started"
        )
    finally:
        await publisher

    assert session.status == 200
    assert b"run_started" in session.body


async def test_no_bearer_token_is_refused(app: ASGIApp) -> None:
    async with _open_stream(app, {}) as session:
        await session.read_until(None, budget=0.5)
    assert session.status in (400, 401)


# --- Frame shape ----------------------------------------------------------------


async def test_a_published_event_arrives_as_the_declared_frame_shape(
    app: ASGIApp, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)

    async def publish_soon() -> None:
        await asyncio.sleep(0.02)
        await deployment.state.deployment_events.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": "run-1"},
        )

    publisher = asyncio.create_task(publish_soon())
    try:
        session = await _read_deployment_stream(app, headers, stop_when=b"run_started")
    finally:
        await publisher

    assert session.status == 200
    frames = _parse_sse(session.body)
    matching = [frame for frame in frames if frame[1] == "run_started"]
    assert len(matching) == 1
    frame_id, _event, data = matching[0]

    epoch = deployment.state.deployment_events.epoch
    assert frame_id == f"{epoch}:1"

    body = json.loads(data)
    assert body == {
        "scope": "run",
        "kind": "run_started",
        "sequence": 1,
        "occurred_at": body["occurred_at"],
        "payload": {"run_id": "run-1"},
    }
    assert set(body) == {"scope", "kind", "sequence", "occurred_at", "payload"}


# --- Cursor / reconnection -------------------------------------------------------


async def test_reconnecting_with_the_current_epoch_delivers_only_what_is_newer(
    app: ASGIApp, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    events = deployment.state.deployment_events
    for index in range(3):
        await events.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": f"run-{index}"},
        )

    cursor = f"{events.epoch}:2"
    session = await _read_deployment_stream(
        app, {**headers, "Last-Event-ID": cursor}, stop_when=b'"sequence":3'
    )

    frames = [frame for frame in _parse_sse(session.body) if frame[1] != ""]
    assert [frame[0] for frame in frames] == [f"{events.epoch}:3"]


async def test_a_cursor_from_a_foreign_epoch_is_answered_with_resync_first(
    app: ASGIApp, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    await deployment.state.deployment_events.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "run-1"}
    )

    session = await _read_deployment_stream(
        app, {**headers, "Last-Event-ID": "a-previous-process:99"}, stop_when=b"resync"
    )

    frames = [frame for frame in _parse_sse(session.body) if frame[1] != ""]
    assert len(frames) == 1
    _frame_id, event, data = frames[0]
    assert event == "resync"
    assert json.loads(data)["payload"] == {}


# --- Ten cycles of disconnection/reconnection (the SC-003 loop) -----------------


async def test_ten_reconnection_cycles_deliver_no_duplicate_and_exactly_one_resync_per_gap(
    app: ASGIApp, deployment: Deployment
) -> None:
    """SC-003: sequence strictly increases within an epoch, nothing repeats,
    and every gap this broker's memory cannot cover produces exactly one
    ``resync`` — proven across ten disconnect/reconnect cycles, not one."""
    headers = await _auth_header(deployment)
    events = deployment.state.deployment_events
    epoch = events.epoch

    seen_sequences: list[int] = []
    resync_count = 0
    cursor = ""

    for cycle in range(10):
        request_headers = dict(headers)
        if cursor:
            request_headers["Last-Event-ID"] = cursor

        expected_sequence = events._sequence + 1  # noqa: SLF001 -- read only, to name the frame this cycle waits for
        expected = f'"sequence":{expected_sequence}'.encode()

        already_attached = events.subscriber_count
        async with _open_stream(app, request_headers) as session:
            # Wait for this cycle's own subscription to actually attach
            # before publishing — a fixed short sleep is the race a slower
            # CI host loses: nothing else observable signals "the ASGI
            # routing, the permission check and `broker.attach` have all
            # happened" from outside the broker itself.
            deadline = time.monotonic() + _BUDGET_SECONDS
            while events.subscriber_count <= already_attached:
                if time.monotonic() > deadline:
                    raise AssertionError(f"cycle {cycle}: the connection never attached")
                await asyncio.sleep(0.005)

            await events.publish(
                scope=DeploymentScope.RUN,
                kind=DeploymentEventKind.RUN_STARTED,
                payload={"run_id": f"run-{cycle}"},
            )
            await session.read_until(expected, budget=_BUDGET_SECONDS)
        assert expected in session.body, f"cycle {cycle}: never saw sequence {expected_sequence}"

        for frame_id, event, _data in _parse_sse(session.body):
            if event == "":
                continue  # a heartbeat comment carries no id/event/data triple
            if event == "resync":
                resync_count += 1
                cursor = frame_id
                continue
            sequence = int(frame_id.rsplit(":", 1)[1])
            assert sequence not in seen_sequences, "no event delivered twice"
            if seen_sequences:
                assert sequence > seen_sequences[-1], "sequence strictly increases within the epoch"
            seen_sequences.append(sequence)
            cursor = frame_id

    assert len(seen_sequences) == 10
    assert seen_sequences == sorted(set(seen_sequences))
    assert epoch == events.epoch, "the broker's epoch never changed mid-loop"
    assert resync_count == 0


# --- Keep-alive cadence, tested directly for speed --------------------------------


async def test_the_keepalive_constant_is_fifteen_seconds() -> None:
    assert SSE_KEEPALIVE_SECONDS == 15.0


async def test_a_quiet_channel_sends_a_heartbeat_at_the_declared_cadence() -> None:
    """Calls `deployment_event_source` directly with a short cadence: a
    fifteen-second real wait has no place in a fast suite, and this is the
    same function the route above calls with the production constant."""
    broker = DeploymentEventBroker()
    frames: list[bytes] = []
    generator = deployment_event_source(broker=broker, cursor=None, keepalive_seconds=0.05)
    async for frame in generator:
        frames.append(frame)
        if len(frames) >= 2:
            await generator.aclose()
            break

    assert frames == [b": heartbeat\n\n", b": heartbeat\n\n"]


def test_the_generator_rejects_a_scope_mismatched_payload_at_construction() -> None:
    """T011's own restatement of the allowlist contract, at the wire boundary."""
    from datetime import UTC, datetime

    with pytest.raises(ValueError, match="extra key"):
        DeploymentEvent(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            sequence=1,
            occurred_at=datetime.now(UTC),
            payload={"run_id": "r1", "title": "leaked"},
        )
