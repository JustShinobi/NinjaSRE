"""A two-hundred-event investigation stays inside every platform's limits.

The number that matters is edits per minute, not events per minute. A long
investigation produces hundreds of events and the discipline is that they
collapse onto one message rewritten on an interval — so the assertion is that
two hundred events cost a number of edits the platform would accept, and that
the final message still says where the run actually ended.

The clock is driven by hand rather than slept through: a test that waited out a
ten-minute investigation to prove a rate would be a test nobody runs.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import (
    CHAT_MAX_EDITS_PER_MINUTE,
    CHAT_STREAM_BENCHMARK_EVENTS,
)
from gateway.chat.port import ChatPlatform, ChatTarget
from gateway.chat.streaming import ProgressSnapshot, ProgressStream
from tests.contract.chat.conftest import RecordingTransport, no_wait

pytestmark = pytest.mark.contract

#: How long the simulated investigation takes. Five minutes of steady output is
#: a long incident run, and it is the window the edit rate is checked over.
RUN_SECONDS = 300.0


class _Clock:
    """A monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


async def _stream_a_long_run(
    platform: ChatPlatform, target: ChatTarget
) -> tuple[ProgressStream, float]:
    """Stream ``CHAT_STREAM_BENCHMARK_EVENTS`` events over ``RUN_SECONDS``.

    Deliberately stops before the final flush. Whether the last event lands on
    an interval boundary differs per platform, so a helper that flushed would
    make every count here one-or-two depending on arithmetic rather than on
    behaviour. Tests that care about the last word flush for themselves.
    """
    clock = _Clock()
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=no_wait)
    await stream.start("investigating…")

    step = RUN_SECONDS / CHAT_STREAM_BENCHMARK_EVENTS
    for index in range(CHAT_STREAM_BENCHMARK_EVENTS):
        clock.advance(step)
        await stream.update(
            ProgressSnapshot(
                stage=f"step {index}",
                capabilities=("kubernetes.pods", "logs.search"),
                elapsed_seconds=clock(),
            )
        )
    return stream, RUN_SECONDS


async def test_two_hundred_events_stay_inside_the_platforms_edit_rate(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    stream, seconds = await _stream_a_long_run(platform, target)
    await stream.flush()

    allowed = CHAT_MAX_EDITS_PER_MINUTE[platform.name]
    per_minute = stream.edits / (seconds / 60.0)

    assert per_minute <= allowed, (
        f"{platform.name} would receive {per_minute:.1f} edits per minute, past its "
        f"budget of {allowed}"
    )


async def test_two_hundred_events_cost_one_message_and_some_edits(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    """The whole discipline in one assertion: one post, not two hundred."""
    stream, _ = await _stream_a_long_run(platform, target)

    assert stream.posts == 1
    assert stream.edits < CHAT_STREAM_BENCHMARK_EVENTS
    assert len(transport.calls) == stream.posts + stream.edits


async def test_nothing_is_dropped_and_the_last_word_is_the_latest(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    stream, _ = await _stream_a_long_run(platform, target)

    # Every event was accounted for when it arrived: written, or coalesced onto
    # a later write. Neither path discards, which is why ``dropped`` is the
    # number that proves nothing was lost, rather than the ratio between the
    # other two.
    assert stream.dropped == 0
    assert stream.edits + stream.coalesced == CHAT_STREAM_BENCHMARK_EVENTS

    await stream.flush()
    assert stream.last_text is not None
    assert f"step {CHAT_STREAM_BENCHMARK_EVENTS - 1}" in stream.last_text


async def test_a_burst_of_events_in_one_second_still_costs_one_edit(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    """An alert storm is the case the interval exists for."""
    clock = _Clock()
    stream = ProgressStream(platform=platform, target=target, clock=clock, sleep=no_wait)
    await stream.start("investigating…")

    clock.advance(stream.interval_seconds + 0.1)
    for index in range(CHAT_STREAM_BENCHMARK_EVENTS):
        await stream.update(ProgressSnapshot(stage=f"burst {index}"))

    assert stream.edits == 1
    assert stream.dropped == 0
