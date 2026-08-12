"""Running the jobs a deployment scheduled.

The defect this covers: ``ScheduledJobWorker`` exists, ``worker_for`` builds
one, and nothing in the codebase ever called ``tick``. A job registered through
``POST /v1/estate/discovery/sources`` was written to the database with a due
time and then sat there — so the estate stayed empty on a deployment that had
been pointed at its cluster, discovery worked when asked by hand, and nothing
said why.

The same silence covered every other kind: ``knowledge.sync``,
``knowledge.corpus_sync`` and ``topology.discovery`` were registerable and
unrunnable for the same reason.
"""

from __future__ import annotations

import asyncio

import pytest

from gateway.http.scheduled_work import run_scheduler

pytestmark = pytest.mark.unit


class _Worker:
    """Counts ticks, and can be told to fail one."""

    def __init__(self, *, fail_on: int = 0) -> None:
        self.ticks = 0
        self._fail_on = fail_on

    async def tick(self) -> tuple[()]:
        self.ticks += 1
        if self.ticks == self._fail_on:
            raise RuntimeError("the store went away mid-tick")
        return ()


async def test_the_loop_ticks_until_it_is_stopped() -> None:
    """A registered job has a due time; something has to come round and claim it."""
    worker = _Worker()
    stop = asyncio.Event()

    async def halt() -> None:
        while worker.ticks < 3:
            await asyncio.sleep(0)
        stop.set()

    await asyncio.gather(
        run_scheduler(worker, interval_seconds=0, stop=stop),
        halt(),
    )

    assert worker.ticks >= 3


async def test_a_tick_that_raises_does_not_end_the_loop() -> None:
    """A scheduler that died on one bad tick would take every recurring job with
    it, and the deployment would look like one that had scheduled nothing."""
    worker = _Worker(fail_on=1)
    stop = asyncio.Event()

    async def halt() -> None:
        while worker.ticks < 3:
            await asyncio.sleep(0)
        stop.set()

    await asyncio.gather(
        run_scheduler(worker, interval_seconds=0, stop=stop),
        halt(),
    )

    assert worker.ticks >= 3


async def test_stopping_is_immediate_rather_than_one_interval_away() -> None:
    """Shutdown must not wait out the interval, or every deployment's restart
    pauses for as long as the slowest schedule."""
    worker = _Worker()
    stop = asyncio.Event()
    stop.set()

    await asyncio.wait_for(run_scheduler(worker, interval_seconds=3600, stop=stop), timeout=1)

    assert worker.ticks == 0
