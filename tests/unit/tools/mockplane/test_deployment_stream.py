"""The mock's deployment-wide channel: no run_id, several scopes, a live poll.

Driven directly against `MockPlane._serve_deployment_stream`, the same way
`test_server.py` drives `stream_frames` directly for the per-run stream —
`max_seconds`/`poll_seconds` are overridable exactly so a test does not pay
this mock's real disconnect-safety budget (`MOCK_DEPLOYMENT_STREAM_MAX_SECONDS`,
thirty seconds) to prove a handful of events arrive.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from tools.mockplane.endpoints import endpoint_by_slug
from tools.mockplane.scenarios import Override
from tools.mockplane.server import DEPLOYMENT_STREAM_EPOCH, MockPlane, StreamControl, build_mock

pytestmark = pytest.mark.unit

_ENDPOINT = endpoint_by_slug("deployment-stream")
_SESSION = "probe"


@pytest.fixture
def mock() -> MockPlane:
    return build_mock("populated")


async def _drive(
    application: MockPlane,
    *,
    headers: dict[str, str] | None = None,
    max_seconds: float = 0.5,
    poll_seconds: float = 0.01,
) -> tuple[int, list[dict[str, Any]]]:
    """Drive `_serve_deployment_stream` directly and return (status, messages)."""
    sent: list[dict[str, Any]] = []

    async def send(message: Any) -> None:
        sent.append(dict(message))

    await application._serve_deployment_stream(  # noqa: SLF001 -- the method under test
        _ENDPOINT,
        headers or {},
        _SESSION,
        send,
        max_seconds=max_seconds,
        poll_seconds=poll_seconds,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    return start["status"], sent


def _bodies(messages: list[dict[str, Any]]) -> bytes:
    return b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )


async def test_the_endpoint_is_declared_streaming_with_no_run_id_in_its_path() -> None:
    assert _ENDPOINT.streaming is True
    assert "{run_id}" not in _ENDPOINT.path
    assert _ENDPOINT.path == "/v1/events/stream"


async def test_served_as_server_sent_events_over_the_wire(mock: MockPlane) -> None:
    status, messages = await _drive(mock, max_seconds=0.05)
    assert status == 200
    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {key.decode(): value.decode() for key, value in start.get("headers", [])}
    assert headers["content-type"] == "text/event-stream"


async def test_a_quiet_session_ends_the_response_at_the_bound_rather_than_hanging(
    mock: MockPlane,
) -> None:
    status, messages = await _drive(mock, max_seconds=0.05, poll_seconds=0.01)
    assert status == 200
    assert messages[-1] == {"type": "http.response.body", "body": b"", "more_body": False}


async def test_a_write_made_while_the_connection_is_open_reaches_it(mock: MockPlane) -> None:
    """The scenario the acceptance spec needs: investigation-start, then a live frame."""

    async def start_investigation_soon() -> None:
        await asyncio.sleep(0.02)
        mock.answer(
            "POST",
            "/v1/investigations",
            session=_SESSION,
            body={"objective": "check the thing"},
        )

    starter = asyncio.create_task(start_investigation_soon())
    try:
        _status, messages = await _drive(mock, max_seconds=1.0, poll_seconds=0.01)
    finally:
        await starter

    body = _bodies(messages)
    assert b"run_started" in body
    assert b'"scope":"run"' in body


async def test_the_frame_id_carries_the_mocks_fixed_epoch(mock: MockPlane) -> None:
    mock.answer("POST", "/v1/investigations", session=_SESSION, body={"objective": "x"})
    _status, messages = await _drive(mock, max_seconds=0.05)
    body = _bodies(messages)
    assert f"id: {DEPLOYMENT_STREAM_EPOCH}:1".encode() in body


async def test_a_cursor_from_a_foreign_epoch_gets_resync_first(mock: MockPlane) -> None:
    mock.answer("POST", "/v1/investigations", session=_SESSION, body={"objective": "x"})
    _status, messages = await _drive(
        mock, headers={"last-event-id": "a-previous-process:99"}, max_seconds=0.05
    )
    body = _bodies(messages)
    assert b"event: resync" in body
    # Content still follows the resync -- the mock does not stop delivering
    # just because it told the client to re-read first.
    assert b"run_started" in body


async def test_a_cursor_in_the_same_epoch_resumes_after_its_position(mock: MockPlane) -> None:
    for _ in range(3):
        mock.answer("POST", "/v1/investigations", session=_SESSION, body={"objective": "x"})
    _status, messages = await _drive(
        mock, headers={"last-event-id": f"{DEPLOYMENT_STREAM_EPOCH}:2"}, max_seconds=0.05
    )
    body = _bodies(messages)
    assert body.count(b"event: run_started") == 1
    assert f"id: {DEPLOYMENT_STREAM_EPOCH}:3".encode() in body


async def test_an_override_refuses_before_any_frame(mock: MockPlane) -> None:
    refusing = mock.with_override(Override(slug="deployment-stream", status=502))
    status, messages = await _drive(refusing, max_seconds=0.05)
    assert status == 502
    assert b"event:" not in _bodies(messages)


async def test_disconnect_after_ends_the_response_early(mock: MockPlane) -> None:
    # `with_stream` returns a MockPlane with its own fresh session store, the
    # same way `with_override` does -- so the control setting has to be in
    # place *before* anything is written to the session it will serve, not
    # applied on top of a mock that already holds the writes.
    dropping = mock.with_stream(StreamControl(disconnect_after=1))
    for _ in range(3):
        dropping.answer("POST", "/v1/investigations", session=_SESSION, body={"objective": "x"})
    _status, messages = await _drive(dropping, max_seconds=0.3, poll_seconds=0.01)
    body = _bodies(messages)
    assert body.count(b"event: run_started") == 1


async def test_a_disruption_ends_an_already_open_connection_early(mock: MockPlane) -> None:
    """`DROP_DEPLOYMENT_STREAM_PATH`'s own reason to exist: a browser test has
    no other way to force a drop on a connection that is already open and
    healthy -- `page.route()` only governs a request made after it is
    registered, and `context.setOffline()` does not sever this mock's
    already-established response either (both tried against this exact
    acceptance spec). This is that mechanism's server-side half, driven the
    same way `test_a_write_made_while_the_connection_is_open_reaches_it`
    drives a concurrent write: the connection opens normally, then the
    disruption lands while its poll loop is already running.
    """

    async def disrupt_soon() -> None:
        await asyncio.sleep(0.03)
        mock.session(_SESSION).deployment_stream_disrupted_until = time.monotonic() + 1.0

    disruptor = asyncio.create_task(disrupt_soon())
    started = time.monotonic()
    try:
        status, messages = await _drive(mock, max_seconds=1.0, poll_seconds=0.01)
    finally:
        await disruptor
    elapsed = time.monotonic() - started

    assert status == 200  # it opened normally, before the disruption landed
    assert _bodies(messages) == b": open\n\n"  # nothing else -- ended right after
    # Ended within a couple of poll ticks of the disruption landing at 0.03s,
    # nowhere near the full second `max_seconds` allows -- proof this is the
    # in-loop check on a connection that was already open, not the refusal a
    # brand new one gets at the top of the method (the next test).
    assert elapsed < 0.3


async def test_a_new_connection_is_refused_during_the_window_and_normal_after(
    mock: MockPlane,
) -> None:
    """The other half: a *reconnection* attempt made while the window is open
    must fail too, or only the connection that happened to be open when the
    drop was requested would ever see it -- the whole point, for the
    acceptance spec's own reconnection scenario, is a handful of consecutive
    failed attempts before recovery.
    """
    mock.session(_SESSION).deployment_stream_disrupted_until = time.monotonic() + 10.0
    refused_status, refused_messages = await _drive(mock, max_seconds=0.05)
    assert refused_status == 502
    assert b"event:" not in _bodies(refused_messages)

    # The window closing, set directly rather than by sleeping past a real
    # ten-second deadline: a connection attempted after it should be served
    # exactly as if no disruption had ever been requested.
    mock.session(_SESSION).deployment_stream_disrupted_until = time.monotonic() - 1.0
    mock.answer("POST", "/v1/investigations", session=_SESSION, body={"objective": "x"})
    recovered_status, recovered_messages = await _drive(mock, max_seconds=0.05)
    assert recovered_status == 200
    assert b"run_started" in _bodies(recovered_messages)

    # And the deadline itself was cleared once passed, not left standing as a
    # stale value every future connection attempt would also have to read.
    assert mock.session(_SESSION).deployment_stream_disrupted_until is None
