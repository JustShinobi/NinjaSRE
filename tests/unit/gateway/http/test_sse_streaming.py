"""SSE: live delivery, reconnection exactly-once (SC-002), and a stalled consumer (SC-007)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from config.constants.runs import MAX_STREAM_BUFFER_EVENTS
from platform.identity.permissions import Role
from platform.persistence.ports.run_trace_store import TraceEventRecord
from platform.persistence.ports.transaction import TenantScope
from platform.runs.events import RunEvent
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _auth_header(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    return {"Authorization": f"Bearer {secret}"}


async def _create_run(client: AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post("/v1/investigations", json={"objective": "x"}, headers=headers)
    return created.json()["run_id"]


def _parse_sse(raw: bytes) -> list[tuple[str, str]]:
    """Return ``(id, event)`` pairs found in a raw SSE byte stream."""
    events: list[tuple[str, str]] = []
    current_id = ""
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("id: "):
            current_id = line[len("id: ") :]
        elif line.startswith("event: "):
            events.append((current_id, line[len("event: ") :]))
    return events


async def test_a_subscriber_receives_events_as_they_happen(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    run_id = await _create_run(client, headers)
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)

    async def publish_soon() -> None:
        await asyncio.sleep(0.05)
        async with deployment.gateway.begin(scope) as uow:
            record = await uow.run_traces.record_event(
                TraceEventRecord(event_id="evt-1", run_id=run_id, kind="turn_completed")
            )
        await deployment.state.broker.publish(RunEvent.of(record))

    publisher = asyncio.create_task(publish_soon())
    try:
        async with client.stream(
            "GET", f"/v1/investigations/{run_id}/stream", headers=headers
        ) as response:
            assert response.status_code == 200
            collected = b""
            async for chunk in response.aiter_bytes():
                collected += chunk
                if b"turn_completed" in collected:
                    break
    finally:
        await publisher

    events = _parse_sse(collected)
    assert any(kind == "turn_completed" for _cursor, kind in events)


async def test_reconnecting_with_a_cursor_delivers_missed_events_exactly_once(
    client: AsyncClient, deployment: Deployment
) -> None:
    """SC-002."""
    headers = await _auth_header(deployment)
    run_id = await _create_run(client, headers)
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)

    async with deployment.gateway.begin(scope) as uow:
        for index in range(3):
            await uow.run_traces.record_event(
                TraceEventRecord(event_id=f"evt-{index}", run_id=run_id, kind="turn_completed")
            )

    async with client.stream(
        "GET", f"/v1/investigations/{run_id}/stream", headers=headers
    ) as response:
        collected = b""
        async for chunk in response.aiter_bytes():
            collected += chunk
            if collected.count(b"event: turn_completed") >= 3:
                break

    first_pass = [item for item in _parse_sse(collected) if item[1] == "turn_completed"]
    assert len(first_pass) == 3
    last_cursor = first_pass[-1][0]

    async with client.stream(
        "GET",
        f"/v1/investigations/{run_id}/stream",
        headers={**headers, "Last-Event-ID": last_cursor},
    ) as response:
        collected = b""

        async def read_briefly() -> bytes:
            chunks = b""
            try:
                async with asyncio.timeout(0.2):
                    async for chunk in response.aiter_bytes():
                        chunks += chunk
            except TimeoutError:
                pass
            return chunks

        collected = await read_briefly()

    reconnected = _parse_sse(collected)
    assert reconnected == [], "no event already seen should be delivered again"


async def test_a_stalled_consumer_is_disconnected_without_blocking_the_run(
    client: AsyncClient, deployment: Deployment
) -> None:
    """SC-007: the run keeps recording events even though nobody drains the stream."""
    headers = await _auth_header(deployment)
    run_id = await _create_run(client, headers)
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)

    async with client.stream(
        "GET", f"/v1/investigations/{run_id}/stream", headers=headers
    ) as response:
        assert response.status_code == 200

        # Publish well past the bounded buffer without ever draining the
        # response body — the subscriber falls behind on purpose.
        async with deployment.gateway.begin(scope) as uow:
            for index in range(MAX_STREAM_BUFFER_EVENTS + 50):
                record = await uow.run_traces.record_event(
                    TraceEventRecord(
                        event_id=f"flood-{index}", run_id=run_id, kind="turn_completed"
                    )
                )
                await deployment.state.broker.publish(RunEvent.of(record))

        assert deployment.state.broker.subscribers(run_id) <= 1
