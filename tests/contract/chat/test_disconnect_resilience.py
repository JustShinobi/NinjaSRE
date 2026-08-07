"""Losing the platform mid-investigation does not fail the run.

Chat is a surface, not the runtime. Everything here asserts the same shape from
a different angle: the sink absorbs the failure, records that it did, and the
report still arrives — on reconnect, or through the fallback sink a deployment
configured for exactly this.

Rate limiting rides along: a refused update backs off and coalesces. It never
drops content, which is asserted by reading what finally went out rather than by
counting calls.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_MAX_DELIVERY_ATTEMPTS
from gateway.chat.port import ChatPlatform, ChatTarget
from gateway.chat.sink import ChatSink, RecordingFallback
from gateway.chat.streaming import ProgressSnapshot, ProgressStream
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import SinkGuard
from tests.contract.chat.conftest import (
    RecordingTransport,
    no_wait,
    rate_limited,
    unavailable,
)

pytestmark = pytest.mark.contract


class _Clock:
    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _Sleeps:
    """Records what a backoff asked to wait for, without waiting."""

    def __init__(self, clock: _Clock) -> None:
        self.waited: list[float] = []
        self._clock = clock

    async def __call__(self, seconds: float) -> None:
        self.waited.append(seconds)
        self._clock.advance(seconds)


# --- The run survives ----------------------------------------------------------


async def test_the_platform_going_away_does_not_raise_into_the_run(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    transport.failures = [unavailable(platform.name) for _ in range(CHAT_MAX_DELIVERY_ATTEMPTS + 2)]
    sink = ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        sleep=no_wait,
    )

    await sink.progress_started("investigating…")
    await sink.progress(ProgressSnapshot(stage="reading logs"))

    assert sink.degraded is True
    assert sink.delivered is False


async def test_the_report_is_delivered_through_the_fallback_when_chat_is_gone(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    transport.failures = [unavailable(platform.name) for _ in range(CHAT_MAX_DELIVERY_ATTEMPTS + 4)]
    fallback = RecordingFallback()
    sink = ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        fallback=fallback,
        sleep=no_wait,
    )

    await sink.report("root cause: the 14:02 deploy rolled out a bad image")

    assert fallback.reports
    assert "14:02" in fallback.reports[0]
    assert sink.degraded is True


async def test_a_platform_that_comes_back_gets_the_report_after_all(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    transport.failures = [unavailable(platform.name), unavailable(platform.name)]
    sink = ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        sleep=no_wait,
    )

    await sink.report("root cause: the 14:02 deploy rolled out a bad image")

    assert sink.delivered is True
    assert any("14:02" in str(call.payload) for call in transport.calls)


async def test_the_bot_being_removed_from_the_channel_is_recorded_not_swallowed(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    transport.failures = [
        unavailable(platform.name, "not_in_channel") for _ in range(CHAT_MAX_DELIVERY_ATTEMPTS + 2)
    ]
    fallback = RecordingFallback()
    sink = ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        fallback=fallback,
        sleep=no_wait,
    )

    await sink.report("root cause: the 14:02 deploy")

    assert sink.last_failure_reason == "not_in_channel"
    assert fallback.reports


# --- Rate limits back off and coalesce, and never drop -------------------------


async def test_a_rate_limited_edit_backs_off_and_still_delivers_the_content(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    clock = _Clock()
    sleeps = _Sleeps(clock)
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=sleeps)
    await stream.start("investigating…")

    transport.failures = [rate_limited(platform.name), rate_limited(platform.name)]
    clock.advance(stream.interval_seconds + 1)
    await stream.update(ProgressSnapshot(stage="correlating deploys"))

    assert sleeps.waited, "a rate limit must be waited out, not retried immediately"
    assert stream.dropped == 0
    assert stream.last_text is not None
    assert "correlating deploys" in stream.last_text


async def test_a_platform_supplied_retry_after_wins_over_the_configured_backoff(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    clock = _Clock()
    sleeps = _Sleeps(clock)
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=sleeps)
    await stream.start("investigating…")

    transport.failures = [rate_limited(platform.name, retry_after_seconds=7.5)]
    clock.advance(stream.interval_seconds + 1)
    await stream.update(ProgressSnapshot(stage="reading logs"))

    assert sleeps.waited[0] == pytest.approx(7.5)


async def test_backoff_doubles_and_stops_at_the_ceiling(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    clock = _Clock()
    sleeps = _Sleeps(clock)
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=sleeps)
    await stream.start("investigating…")

    transport.failures = [rate_limited(platform.name) for _ in range(CHAT_MAX_DELIVERY_ATTEMPTS)]
    clock.advance(stream.interval_seconds + 1)
    await stream.update(ProgressSnapshot(stage="reading logs"))

    assert sleeps.waited == sorted(sleeps.waited)
    assert len(set(sleeps.waited)) > 1


async def test_updates_arriving_during_a_backoff_coalesce_rather_than_queue(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    clock = _Clock()
    sleeps = _Sleeps(clock)
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=sleeps)
    await stream.start("investigating…")

    for index in range(200):
        await stream.update(ProgressSnapshot(stage=f"stage {index}"))
    clock.advance(stream.interval_seconds + 1)
    await stream.flush()

    assert stream.dropped == 0
    assert stream.last_text is not None
    assert "stage 199" in stream.last_text
