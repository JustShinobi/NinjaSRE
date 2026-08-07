"""T041: background handling, and reaping it correctly.

Three properties, and each of them is a bug that only shows up under load or at
shutdown — which is to say, in production and not in review:

- a task nobody holds a reference to can be collected mid-await;
- a task that swallows ``CancelledError`` makes shutdown hang;
- a task whose exception is never retrieved makes asyncio log a warning nobody
  can attribute.
"""

from __future__ import annotations

import asyncio
import gc
from collections.abc import Mapping
from typing import Any

import pytest

from gateway.discord.worker import DiscordWorker

pytestmark = pytest.mark.unit


class _Handler:
    """A handler the test drives: it waits until released, or fails, or hangs."""

    def __init__(self, *, fail: bool = False, hang: bool = False) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = 0
        self.cancelled = 0
        self.fail = fail
        self.hang = hang
        self.concurrent = 0
        self.peak = 0

    async def __call__(self, payload: Mapping[str, Any]) -> None:
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        self.started.set()
        try:
            if self.fail:
                raise RuntimeError("handler exploded")
            if self.hang:
                await asyncio.Event().wait()
            else:
                await self.release.wait()
            self.finished += 1
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.concurrent -= 1


PAYLOAD: Mapping[str, Any] = {"t": "MESSAGE_CREATE", "d": {"id": "1"}}


# --- The reference is held --------------------------------------------------------


async def test_a_dispatched_task_is_held_while_it_runs() -> None:
    handler = _Handler()
    worker = DiscordWorker(handler=handler)

    worker.dispatch(PAYLOAD)
    await handler.started.wait()
    gc.collect()

    assert worker.in_flight == 1

    handler.release.set()
    await worker.close()
    assert handler.finished == 1
    assert worker.handled == 1


async def test_a_finished_task_stops_being_held() -> None:
    handler = _Handler()
    worker = DiscordWorker(handler=handler)

    task = worker.dispatch(PAYLOAD)
    handler.release.set()
    assert task is not None
    await task

    assert worker.in_flight == 0


# --- One failure does not stop the connection --------------------------------------


async def test_a_failing_handler_is_counted_and_the_worker_keeps_going() -> None:
    failing = DiscordWorker(handler=_Handler(fail=True))

    task = failing.dispatch(PAYLOAD)
    assert task is not None
    await task

    assert failing.failed == 1
    assert failing.handled == 0
    # The exception was retrieved, so asyncio has nothing to complain about.
    assert task.exception() is None


async def test_a_second_payload_is_still_handled_after_a_failure() -> None:
    handler = _Handler(fail=True)
    worker = DiscordWorker(handler=handler)

    first = worker.dispatch(PAYLOAD)
    assert first is not None
    await first
    handler.fail = False
    handler.release.set()
    second = worker.dispatch(PAYLOAD)
    assert second is not None
    await second

    assert worker.failed == 1
    assert worker.handled == 1


# --- Concurrency is bounded ---------------------------------------------------------


async def test_no_more_than_the_configured_number_run_at_once() -> None:
    handler = _Handler()
    worker = DiscordWorker(handler=handler, max_concurrent=2)

    for _ in range(6):
        worker.dispatch(PAYLOAD)
    await handler.started.wait()
    await asyncio.sleep(0)
    peak_while_blocked = handler.peak

    handler.release.set()
    await worker.close()

    assert peak_while_blocked <= 2
    assert handler.peak <= 2


# --- Shutdown -----------------------------------------------------------------------


async def test_closing_waits_for_what_is_running() -> None:
    handler = _Handler()
    worker = DiscordWorker(handler=handler)

    worker.dispatch(PAYLOAD)
    await handler.started.wait()
    handler.release.set()
    await worker.close()

    assert handler.finished == 1
    assert worker.in_flight == 0


async def test_closing_cancels_what_will_not_finish_and_the_cancel_lands() -> None:
    handler = _Handler(hang=True)
    worker = DiscordWorker(handler=handler, drain_timeout_seconds=0.01)

    worker.dispatch(PAYLOAD)
    await handler.started.wait()
    await worker.close()

    assert handler.cancelled == 1
    assert worker.cancelled == 1
    assert worker.in_flight == 0


async def test_nothing_new_is_accepted_once_closing_has_started() -> None:
    handler = _Handler(hang=True)
    worker = DiscordWorker(handler=handler, drain_timeout_seconds=0.01)

    worker.dispatch(PAYLOAD)
    await handler.started.wait()
    await worker.close()

    assert worker.dispatch(PAYLOAD) is None


async def test_closing_an_idle_worker_is_a_no_op() -> None:
    worker = DiscordWorker(handler=_Handler())

    await worker.close()

    assert worker.in_flight == 0
