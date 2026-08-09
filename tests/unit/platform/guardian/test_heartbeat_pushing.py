"""The push itself: that it happens, that it is bounded, and that it cannot be turned off.

FR-028 is unusually emphatic — "not optional and has no configuration that
disables it while the guardian is enabled" — and the reason is a real incident:
both nodes of a two-node cluster lost networking, the entire observability stack
was on one of them, and not a single alert fired. So these tests are about the
push being real rather than declared, and about the two ways it could quietly
stop being real: a destination nobody set, and a failure nobody noticed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.guardian import HEARTBEAT_INTERVAL_SECONDS
from platform.guardian.heartbeat import HeartbeatPusher, HeartbeatUndeliverable

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 7, 3, 14, tzinfo=UTC)


class Recorder:
    """A transport that remembers what it was handed."""

    def __init__(self) -> None:
        self.pushed: list[dict[str, object]] = []

    async def push(self, destination: str, payload: dict[str, object]) -> None:
        """Record one heartbeat."""
        self.pushed.append({"destination": destination, **payload})


class Broken:
    """A transport that never takes anything."""

    async def push(self, destination: str, payload: dict[str, object]) -> None:
        """Refuse, the way an unreachable destination does."""
        raise HeartbeatUndeliverable("the destination refused the connection")


async def test_a_heartbeat_is_pushed_to_the_destination_the_operator_chose() -> None:
    recorder = Recorder()
    pusher = HeartbeatPusher(transport=recorder, destination="https://watch.example/abc")

    await pusher.push(at=NOW, open_incidents=2)

    assert recorder.pushed[0]["destination"] == "https://watch.example/abc"
    assert recorder.pushed[0]["open_incidents"] == 2


async def test_the_sequence_advances_so_a_watcher_can_see_a_gap() -> None:
    """A watcher that only saw timestamps could not tell a missed push from a
    clock that moved."""
    recorder = Recorder()
    pusher = HeartbeatPusher(transport=recorder, destination="https://watch.example/abc")

    await pusher.push(at=NOW)
    await pusher.push(at=NOW + timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS))

    assert [entry["sequence"] for entry in recorder.pushed] == [1, 2]


async def test_a_push_is_due_on_the_interval_and_not_before_it() -> None:
    """Nothing here owns a timer. Whatever drives the deployment's clock asks."""
    pusher = HeartbeatPusher(transport=Recorder(), destination="https://watch.example/abc")

    assert pusher.is_due(NOW), "the first one is always due"
    await pusher.push(at=NOW)
    assert not pusher.is_due(NOW + timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS / 2))
    assert pusher.is_due(NOW + timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS))


async def test_a_deployment_that_knows_it_is_unwell_says_so_in_the_heartbeat() -> None:
    """So a watcher can tell "still alive and unhappy" from "still alive"."""
    recorder = Recorder()
    pusher = HeartbeatPusher(transport=recorder, destination="https://watch.example/abc")

    await pusher.push(at=NOW, degraded_because="pve01 is unreachable and I am a guest of it")

    assert recorder.pushed[0]["healthy"] is False
    assert "guest of it" in str(recorder.pushed[0]["degraded_because"])


async def test_a_push_that_did_not_land_is_recorded_rather_than_swallowed() -> None:
    """A dead-man's switch whose own failures were silent would be the second copy
    of the problem it exists to catch."""
    pusher = HeartbeatPusher(transport=Broken(), destination="https://watch.example/abc")

    with pytest.raises(HeartbeatUndeliverable):
        await pusher.push(at=NOW)

    assert pusher.consecutive_failures == 1
    assert not pusher.last_push_landed


async def test_a_failed_push_does_not_advance_the_sequence() -> None:
    """Otherwise the watcher sees a gap and the deployment thinks it pushed."""
    pusher = HeartbeatPusher(transport=Broken(), destination="https://watch.example/abc")

    with pytest.raises(HeartbeatUndeliverable):
        await pusher.push(at=NOW)

    assert pusher.sequence == 0
    assert pusher.is_due(NOW), "still owed, so the next tick tries again"


async def test_there_is_no_way_to_construct_an_enabled_pusher_with_nowhere_to_push() -> None:
    """FR-028: no configuration disables it while the guardian is enabled. The
    only setting is *where*, and an empty one is refused rather than treated as
    "off" — which is what a disable switch would look like if there were one."""
    with pytest.raises(ValueError, match="destination"):
        HeartbeatPusher(transport=Recorder(), destination="")


async def test_the_pusher_reports_what_a_health_endpoint_needs_to_say() -> None:
    recorder = Recorder()
    pusher = HeartbeatPusher(transport=recorder, destination="https://watch.example/abc")
    await pusher.push(at=NOW)

    record = pusher.to_record()

    assert record["pushes"] == 1
    assert record["consecutive_failures"] == 0
    assert record["destination_configured"] is True
    assert "watch.example" not in str(record), "the destination is a secret-ish URL"
