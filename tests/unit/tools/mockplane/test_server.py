"""The mock itself: paths, failures, streams, session writes, and the network it refuses.

Driven two ways on purpose. Most of these call ``answer`` directly, which is the
programmatic entry point a test harness uses; the ASGI ones go through the real
protocol, because a mock whose two entry points disagreed would be a mock that
passed its own tests and failed the console.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

import pytest

from tools.mockplane.scenarios import Override
from tools.mockplane.server import (
    SESSION_HEADER,
    MockPlane,
    OutboundRequestRefused,
    StreamControl,
    build_mock,
    no_outbound_network,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def mock() -> MockPlane:
    return build_mock("populated")


async def call(
    application: MockPlane,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    """Drive the application over the real ASGI protocol and return what it sent."""
    payload = json.dumps(body).encode() if body is not None else b""
    messages = [{"type": "http.request", "body": payload, "more_body": False}]

    async def receive() -> dict[str, Any]:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    sent: list[dict[str, Any]] = []

    async def send(message: Any) -> None:
        sent.append(dict(message))

    await application(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(key.encode(), value.encode()) for key, value in (headers or {}).items()],
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    chunks = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return (
        start["status"],
        chunks,
        {key.decode(): value.decode() for key, value in start.get("headers", [])},
    )


# --- Path, method and status fidelity ---------------------------------------------


def test_it_answers_on_the_gateways_own_paths(mock: MockPlane) -> None:
    assert mock.answer("GET", "/v1/runs").status == 200
    assert mock.answer("GET", "/auth/me").status == 200
    assert mock.answer("GET", "/health/ready").status == 200


def test_a_templated_path_resolves_to_the_record_for_that_identifier(mock: MockPlane) -> None:
    answer = mock.answer("GET", "/v1/runs/run-0001")
    assert json.loads(answer.body)["run_id"] == "run-0001"


def test_a_query_string_does_not_stop_a_path_resolving(mock: MockPlane) -> None:
    assert mock.answer("GET", "/v1/runs?limit=5").status == 200


def test_a_path_nothing_serves_is_a_404_rather_than_a_fallthrough(mock: MockPlane) -> None:
    answer = mock.answer("GET", "/v1/not-a-thing")
    assert answer.status == 404
    assert b"not an endpoint this mock serves" in answer.body


def test_a_write_answers_the_status_the_document_declares(mock: MockPlane) -> None:
    assert mock.answer("POST", "/v1/investigations", body={"objective": "x"}).status == 202
    assert mock.answer("POST", "/identity/tokens", body={"name": "x"}).status == 201


def test_the_projected_endpoints_answer_too(mock: MockPlane) -> None:
    for path in ("/v1/estate/resources", "/v1/estate/storage", "/v1/incidents", "/v1/detectors"):
        assert mock.answer("GET", path).status == 200, path


# --- Injected failure -------------------------------------------------------------


def test_an_injected_status_replaces_the_answer(mock: MockPlane) -> None:
    failing = mock.with_override(Override(slug="runs", status=500))
    answer = failing.answer("GET", "/v1/runs")
    assert answer.status == 500
    assert b"unhappy" in answer.body


def test_an_injected_latency_is_reported_rather_than_slept_through(mock: MockPlane) -> None:
    slow = mock.with_override(Override(slug="runs", latency_ms=1500))
    assert slow.answer("GET", "/v1/runs").latency_ms == 1500


def test_an_injected_empty_answer_keeps_the_shape_and_loses_the_records(
    mock: MockPlane,
) -> None:
    emptied = mock.with_override(Override(slug="runs", empty=True))
    assert json.loads(emptied.answer("GET", "/v1/runs").body) == {"runs": []}


def test_a_truncated_answer_is_not_valid_json(mock: MockPlane) -> None:
    truncated = mock.with_override(Override(slug="runs", truncate=True))
    answer = truncated.answer("GET", "/v1/runs")
    with pytest.raises(json.JSONDecodeError):
        json.loads(answer.body)


def test_a_refused_endpoint_says_it_refused_rather_than_answering(mock: MockPlane) -> None:
    refused = mock.with_override(Override(slug="runs", refuse=True))
    assert refused.answer("GET", "/v1/runs").refuse is True


async def test_a_refused_endpoint_closes_the_connection_with_nothing_on_it(
    mock: MockPlane,
) -> None:
    refused = mock.with_override(Override(slug="runs", refuse=True))
    status, body, _ = await call(refused, "GET", "/v1/runs")
    assert status == 502
    assert body == b""


def test_the_degraded_scenario_fails_the_endpoints_it_declares() -> None:
    degraded = build_mock("degraded")
    assert degraded.answer("GET", "/v1/incidents").status == 500
    assert degraded.answer("GET", "/audit/events").status == 403
    assert degraded.answer("GET", "/v1/topology/svc-ledger").status == 404
    assert degraded.answer("GET", "/v1/estate/storage").latency_ms > 0


def test_the_degraded_scenario_leaves_the_rest_alone() -> None:
    assert build_mock("degraded").answer("GET", "/v1/runs").status == 200


# --- Streaming --------------------------------------------------------------------


async def collect(frames: AsyncIterator[bytes]) -> list[bytes]:
    return [frame async for frame in frames]


async def test_the_stream_emits_one_frame_per_event(mock: MockPlane) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    frames = await collect(fast.stream_frames("run-0003"))
    assert len(frames) == len(mock.events_for("run-0003"))
    assert frames[0].startswith(b"id: run-0003:0\n")


async def test_every_frame_carries_the_cursor_a_client_resumes_from(mock: MockPlane) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    frames = await collect(fast.stream_frames("run-0003"))
    for frame in frames:
        assert frame.startswith(b"id: run-0003:")
        assert b"\ndata: {" in frame


async def test_the_stream_can_be_made_to_disconnect_in_the_middle(mock: MockPlane) -> None:
    dropping = mock.with_stream(StreamControl(events_per_second=0, disconnect_after=3))
    frames = await collect(dropping.stream_frames("run-0003"))
    assert len(frames) == 3


async def test_a_reconnection_resumes_after_the_cursor_it_presents(mock: MockPlane) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    resumed = await collect(fast.stream_frames("run-0003", after=2))
    assert resumed
    assert resumed[0].startswith(b"id: run-0003:3\n")


async def test_nothing_is_lost_or_repeated_across_a_disconnection(mock: MockPlane) -> None:
    dropping = mock.with_stream(StreamControl(events_per_second=0, disconnect_after=3))
    first = await collect(dropping.stream_frames("run-0003"))
    last_seen = int(first[-1].split(b"\n")[0].rsplit(b":", 1)[1])

    fast = mock.with_stream(StreamControl(events_per_second=0))
    resumed = await collect(fast.stream_frames("run-0003", after=last_seen))

    sequences = [int(frame.split(b"\n")[0].rsplit(b":", 1)[1]) for frame in (*first, *resumed)]
    assert sequences == sorted(sequences), "the events came back out of order"
    assert len(sequences) == len(set(sequences)), "an event was delivered twice"
    assert sequences == list(range(len(sequences))), "an event was lost across the reconnection"


async def test_a_reconnection_with_no_cursor_replays_from_the_start(mock: MockPlane) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    assert (await collect(fast.stream_frames("run-0003")))[0].startswith(b"id: run-0003:0\n")


async def test_the_stream_is_served_as_server_sent_events_over_the_wire(
    mock: MockPlane,
) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    status, body, headers = await call(fast, "GET", "/v1/investigations/run-0003/stream")
    assert status == 200
    assert headers["content-type"] == "text/event-stream"
    assert body.startswith(b"id: run-0003:0\n")


async def test_the_last_event_id_header_is_what_a_resume_reads(mock: MockPlane) -> None:
    fast = mock.with_stream(StreamControl(events_per_second=0))
    _, body, _ = await call(
        fast,
        "GET",
        "/v1/investigations/run-0003/stream",
        headers={"last-event-id": "run-0003:4"},
    )
    assert body.startswith(b"id: run-0003:5\n")


def test_the_event_rate_is_controllable(mock: MockPlane) -> None:
    assert mock.with_stream(StreamControl(events_per_second=100))._stream.events_per_second == 100


# --- Session-scoped writes --------------------------------------------------------


def test_a_write_is_reflected_in_the_next_read(mock: MockPlane) -> None:
    before = len(json.loads(mock.answer("GET", "/v1/runs").body)["runs"])
    mock.answer("POST", "/v1/investigations", body={"objective": "look at the volume"})
    after = json.loads(mock.answer("GET", "/v1/runs").body)["runs"]
    assert len(after) == before + 1
    assert after[0]["run_id"] == "run-0007"


def test_approving_an_interaction_closes_it_on_the_next_read(mock: MockPlane) -> None:
    mock.answer("POST", "/v1/interactions/int-0002/approve")
    interactions = json.loads(mock.answer("GET", "/v1/investigations/run-0005/interactions").body)[
        "interactions"
    ]
    assert interactions[0]["is_open"] is False
    assert interactions[0]["reason"] == "approved"


def test_a_configuration_write_is_reflected_in_the_effective_view(mock: MockPlane) -> None:
    mock.answer(
        "PUT",
        "/v1/config/env-production",
        body={"patch": {"investigation.max_loops": 16}},
    )
    effective = json.loads(mock.answer("GET", "/v1/config/env-production").body)
    assert effective["values"]["investigation.max_loops"] == 16
    assert effective["provenance"]["investigation.max_loops"] == "env-production"


def test_revoking_a_token_is_reflected_in_the_next_read(mock: MockPlane) -> None:
    mock.answer("POST", "/identity/tokens/revoke", body={"token_ids": ["tok-0002"]})
    tokens = json.loads(mock.answer("GET", "/identity/tokens").body)["tokens"]
    assert next(token for token in tokens if token["token_id"] == "tok-0002")["revoked"] is True


def test_one_session_does_not_see_another_session_s_writes(mock: MockPlane) -> None:
    mock.answer("POST", "/v1/investigations", body={"objective": "x"}, session="alice")
    theirs = json.loads(mock.answer("GET", "/v1/runs", session="bob").body)["runs"]
    assert all(run["run_id"] != "run-0007" for run in theirs)


def test_a_reset_forgets_everything_written(mock: MockPlane) -> None:
    before = mock.answer("GET", "/v1/runs").body
    mock.answer("POST", "/v1/investigations", body={"objective": "x"})
    mock.reset()
    assert mock.answer("GET", "/v1/runs").body == before


async def test_the_session_header_separates_two_clients_over_the_wire(mock: MockPlane) -> None:
    await call(
        mock,
        "POST",
        "/v1/investigations",
        body={"objective": "x"},
        headers={SESSION_HEADER: "alice"},
    )
    _, body, _ = await call(mock, "GET", "/v1/runs", headers={SESSION_HEADER: "bob"})
    assert all(run["run_id"] != "run-0007" for run in json.loads(body)["runs"])


# --- Determinism ------------------------------------------------------------------


def test_serving_one_scenario_twice_is_byte_identical_timestamps_included() -> None:
    first = build_mock("populated")
    second = build_mock("populated")
    for path in ("/v1/runs", "/v1/approvals", "/v1/estate/resources", "/audit/events"):
        assert first.answer("GET", path).body == second.answer("GET", path).body, path


async def test_the_two_entry_points_agree(mock: MockPlane) -> None:
    # ``answer`` is what a test drives; the ASGI application is what the console
    # reaches. Both must say the same thing or the tests prove nothing.
    direct = mock.answer("GET", "/v1/runs")
    status, body, _ = await call(mock, "GET", "/v1/runs")
    assert (status, body) == (direct.status, direct.body)


# --- The network it refuses -------------------------------------------------------


def test_an_outbound_request_fails_loudly() -> None:
    with no_outbound_network(), pytest.raises((OutboundRequestRefused, urllib.error.URLError)):
        urllib.request.urlopen("http://127.0.0.1:9/nothing", timeout=1)


def test_a_raw_socket_connection_fails_loudly() -> None:
    with no_outbound_network(), pytest.raises(OutboundRequestRefused):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


def test_the_refusal_names_what_was_reached_for() -> None:
    with no_outbound_network():
        try:
            socket.create_connection(("metrics.example.invalid", 443), timeout=1)
        except OutboundRequestRefused as refusal:
            assert "metrics.example.invalid" in str(refusal)
        else:  # pragma: no cover - the assertion above is the point
            pytest.fail("the connection was not refused")


def test_the_network_works_again_afterwards() -> None:
    with no_outbound_network():
        pass
    assert socket.socket.connect is not None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 9), timeout=0.2)


def test_the_mock_itself_needs_no_network_at_all() -> None:
    with no_outbound_network():
        assert build_mock("populated").answer("GET", "/v1/runs").status == 200
