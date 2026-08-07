"""Background handling for one gateway connection, and reaping what it started.

An investigation takes minutes and Discord's interaction callback window is
three seconds, so handling cannot happen on the socket's own task. Everything
inbound is therefore acknowledged and dispatched to a background task — and a
background task nobody holds a reference to is one the garbage collector may
finish before it does, which is the specific failure this module exists to make
impossible.

**Cancellation is the normal path, not an error.** Shutting down cancels every
task in flight, and a cancelled task that swallowed its ``CancelledError`` would
leave the loop unable to stop. So cancellation propagates, and reaping waits for
it rather than assuming it happened.

**One failing handler does not stop the connection.** A payload nobody could
parse is logged with its type name and the socket keeps delivering, because the
alternative — the whole surface going quiet because one guild sent something
odd — is worse than a missed message.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: How long shutdown waits for handlers already running to finish before it
#: stops waiting and reports what was still in flight.
DRAIN_TIMEOUT_SECONDS: Final = 10.0

#: Handlers allowed to run at once. A guild-wide alert storm otherwise starts one
#: task per event, and the first thing to fall over is the process rather than
#: the rate limiter.
MAX_CONCURRENT_HANDLERS: Final = 16

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class DiscordWorker:
    """Runs inbound handling off the socket task, and cleans up after itself."""

    handler: Handler
    max_concurrent: int = MAX_CONCURRENT_HANDLERS
    drain_timeout_seconds: float = DRAIN_TIMEOUT_SECONDS

    handled: int = field(default=0, init=False)
    failed: int = field(default=0, init=False)
    cancelled: int = field(default=0, init=False)
    #: Strong references to everything in flight. Without this the event loop
    #: holds only a weak one and a task can be collected mid-await.
    _running: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)
    _limit: asyncio.Semaphore = field(init=False, repr=False)
    _closing: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._limit = asyncio.Semaphore(self.max_concurrent)

    @property
    def in_flight(self) -> int:
        """Return how many handlers are running right now."""
        return len(self._running)

    def dispatch(self, payload: Mapping[str, Any]) -> asyncio.Task[None] | None:
        """Start handling ``payload`` in the background and return its task.

        Returns ``None`` once the worker is closing: a payload accepted during
        shutdown would be one nothing is going to wait for.
        """
        if self._closing:
            logger.info("discord.payload_dropped_while_closing")
            return None
        task = asyncio.create_task(self._run(payload))
        self._running.add(task)
        task.add_done_callback(self._reap)
        return task

    async def _run(self, payload: Mapping[str, Any]) -> None:
        """Run one handler under the concurrency bound."""
        async with self._limit:
            try:
                await self.handler(payload)
            except asyncio.CancelledError:
                # Propagated, never swallowed: a task that absorbed this would
                # make shutdown hang on a loop that cannot be stopped.
                self.cancelled += 1
                raise
            except Exception as failure:  # noqa: BLE001 — one payload must not stop the socket
                self.failed += 1
                logger.error("discord.handler_failed", error=type(failure).__name__)
            else:
                self.handled += 1

    def _reap(self, task: asyncio.Task[None]) -> None:
        """Drop a finished task's reference and consume its exception.

        Reading the exception is what stops asyncio logging "task exception was
        never retrieved" for a failure this worker has already counted.
        """
        self._running.discard(task)
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            logger.error("discord.task_failed", error=type(failure).__name__)

    async def close(self) -> None:
        """Stop accepting work, wait for what is running, then cancel the rest."""
        self._closing = True
        if not self._running:
            return
        pending = tuple(self._running)
        done, still_running = await asyncio.wait(pending, timeout=self.drain_timeout_seconds)
        for task in still_running:
            task.cancel()
        for task in still_running:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if still_running:
            logger.warning(
                "discord.workers_cancelled_at_shutdown",
                finished=len(done),
                cancelled=len(still_running),
            )
        self._running.clear()


__all__ = [
    "DRAIN_TIMEOUT_SECONDS",
    "MAX_CONCURRENT_HANDLERS",
    "DiscordWorker",
    "Handler",
]
