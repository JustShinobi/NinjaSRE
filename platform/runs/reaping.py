"""Closing the runs whose process is gone.

A run's status is written by the process driving it. So a process that is
killed — a pod evicted mid-deploy, a node lost, an out-of-memory kill — leaves
a row saying ``running`` that nothing will ever correct. The graceful path
already exists on the way down: ``gateway.http.lifespan.drain`` asks every
in-flight run to stop at its next safe point. What it cannot cover is the way a
process actually dies most of the time, which is not gracefully.

``RunStatus.INTERRUPTED`` was written for exactly this, and says so: *"written
for a run by whoever noticed it stopped — a reaper finding an expired lease, a
replica finding a run still marked running at boot"*. This is that replica.

**The bound is the wall clock, not the boot.** A booting replica must not close
runs another replica is driving right now, and it cannot tell them apart by
asking. What it can do is arithmetic: a run has a wall-clock ceiling, so a run
older than that ceiling is one no process is still inside, whoever is booting.
Sweeping on age rather than on "I am starting" is what makes this safe to run in
a deployment with more than one replica, and it is why the margin is added
rather than the ceiling used bare.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from config.constants.investigation import RUN_WALL_CLOCK_SECONDS
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, RunTraceStore
from platform.runs.recorder import RunRecorder

logger = get_logger(__name__)

#: Added to the wall-clock ceiling before a run is considered abandoned. A run
#: at exactly the ceiling may be in the act of recording its own ending, and
#: interrupting that would overwrite a real outcome with "nobody knows".
REAP_MARGIN_SECONDS: Final = 300.0

#: What is written as the interruption's reason. One sentence, because it is
#: what an operator meets in the run's own history.
REAP_REASON = (
    "the process driving this run is gone: it was still marked running longer than a run "
    "can last, so whatever it was doing ended without being recorded"
)

#: The states a run can be abandoned in. ``SUSPENDED`` is included because a run
#: paused for a takeover is also held in a process, and that process dies the
#: same way.
UNFINISHED = (RunStatus.RUNNING, RunStatus.SUSPENDED)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(slots=True)
class RunReaper:
    """Finds runs no process can still be inside, and records that nobody knows."""

    recorder: RunRecorder
    store: RunTraceStore
    clock: Callable[[], datetime] = field(default=_utc_now)
    #: How far past the wall-clock ceiling a run must be. Named so a test can
    #: shorten it without moving the clock a whole hour.
    margin_seconds: float = REAP_MARGIN_SECONDS

    def abandoned(self, runs: Sequence[AgentRun], *, now: datetime) -> tuple[AgentRun, ...]:
        """Return the runs in ``runs`` that no process can still be driving."""
        cutoff = now - timedelta(seconds=RUN_WALL_CLOCK_SECONDS + self.margin_seconds)
        return tuple(
            run
            for run in runs
            if run.status in UNFINISHED and run.started_at is not None and run.started_at < cutoff
        )

    async def reap(self, *, limit: int = 200) -> tuple[str, ...]:
        """Close every abandoned run and return the identifiers that were closed.

        Never raises into the caller. This runs at startup, and a store that
        cannot answer is a reason to serve without having tidied rather than a
        reason not to serve — the rows it would have corrected are wrong either
        way, and refusing to boot over them makes that worse.
        """
        now = self.clock()
        closed: list[str] = []
        for status in UNFINISHED:
            try:
                found = await self.store.list_runs(status=status, limit=limit)
            except Exception as unreadable:  # noqa: BLE001 — tidying must not stop a boot
                logger.warning("runs.reap_read_failed", status=status.value, error=str(unreadable))
                continue
            for run in self.abandoned(found, now=now):
                try:
                    await self.recorder.mark_interrupted(run.run_id, reason=REAP_REASON)
                except Exception as unwritable:  # noqa: BLE001 — one row must not stop the rest
                    logger.warning(
                        "runs.reap_write_failed", run_id=run.run_id, error=str(unwritable)
                    )
                    continue
                closed.append(run.run_id)
        if closed:
            logger.warning("runs.reaped", count=len(closed), run_ids=closed)
        return tuple(closed)
