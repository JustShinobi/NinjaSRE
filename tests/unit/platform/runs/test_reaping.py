"""Which runs a booting replica may close, and which it must leave alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from config.constants.investigation import RUN_WALL_CLOCK_SECONDS
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.runs.reaping import REAP_MARGIN_SECONDS, RunReaper

NOW = datetime(2026, 8, 26, 1, 30, tzinfo=UTC)


def _run(run_id: str, *, age_seconds: float, status: RunStatus = RunStatus.RUNNING) -> AgentRun:
    """Return a stored run that started ``age_seconds`` ago."""
    return AgentRun(
        run_id=run_id,
        trigger="alert",
        status=status,
        started_at=NOW - timedelta(seconds=age_seconds),
    )


def test_a_run_older_than_a_run_can_last_is_one_no_process_is_inside() -> None:
    """Measured against staging on 2026-08-26: nine runs marked running, one for three days.

    A run's status is written by the process driving it, so a pod evicted
    mid-deploy leaves a row that says running for ever. Six of those nine
    started in the same second, which is a redeploy; one had been "running"
    since 22 August.
    """
    reaper = RunReaper(recorder=cast(Any, object()), store=cast(Any, object()))
    stale = _run("three-days", age_seconds=3 * 24 * 3600)

    assert reaper.abandoned([stale], now=NOW) == (stale,)


def test_a_run_still_inside_its_own_ceiling_is_left_alone() -> None:
    """The bound is arithmetic, not "I am booting".

    A replica cannot ask another replica whether it is driving a run, so it must
    not close one that could still be live. A run below the ceiling could be,
    and is left where it is — which is what makes this safe to run at every
    boot in a deployment with more than one replica.
    """
    reaper = RunReaper(recorder=cast(Any, object()), store=cast(Any, object()))
    live = _run("still-going", age_seconds=RUN_WALL_CLOCK_SECONDS / 2)

    assert reaper.abandoned([live], now=NOW) == ()


def test_a_run_at_the_ceiling_keeps_the_margin_to_record_its_own_ending() -> None:
    """A run finishing right now is recording an outcome, and it is the real one.

    Interrupting it would overwrite what actually happened with "nobody knows",
    which is worse than the row being briefly wrong.
    """
    reaper = RunReaper(recorder=cast(Any, object()), store=cast(Any, object()))
    finishing = _run("just-at-the-line", age_seconds=RUN_WALL_CLOCK_SECONDS + 1)

    assert reaper.abandoned([finishing], now=NOW) == ()

    past = _run("past-the-margin", age_seconds=RUN_WALL_CLOCK_SECONDS + REAP_MARGIN_SECONDS + 1)
    assert reaper.abandoned([past], now=NOW) == (past,)


def test_a_suspended_run_is_abandoned_too_because_it_is_held_in_a_process() -> None:
    """A takeover pauses a run inside the process driving it, and that process dies too."""
    reaper = RunReaper(recorder=cast(Any, object()), store=cast(Any, object()))
    paused = _run("paused", age_seconds=2 * 24 * 3600, status=RunStatus.SUSPENDED)

    assert reaper.abandoned([paused], now=NOW) == (paused,)


def test_a_finished_run_is_never_touched() -> None:
    """Its outcome is recorded; there is nothing for a reaper to say about it."""
    reaper = RunReaper(recorder=cast(Any, object()), store=cast(Any, object()))
    done = _run("done", age_seconds=5 * 24 * 3600, status=RunStatus.COMPLETED)

    assert reaper.abandoned([done], now=NOW) == ()


async def test_reap_pages_through_all_abandoned_runs() -> None:
    """When more abandoned runs exist than one page limit, all pages are reaped."""
    runs_db = [
        _run(f"run-{i}", age_seconds=5 * 24 * 3600, status=RunStatus.RUNNING) for i in range(5)
    ]
    interrupted: list[str] = []

    class FakeStore:
        async def list_runs(
            self, *, status: RunStatus | None = None, until: datetime | None = None, limit: int = 50
        ) -> tuple[AgentRun, ...]:
            remaining = [
                r
                for r in runs_db
                if r.status == status and (until is None or (r.started_at and r.started_at < until))
            ]
            return tuple(remaining[:limit])

    class FakeRecorder:
        async def mark_interrupted(self, run_id: str, *, reason: str) -> None:
            interrupted.append(run_id)
            for i, r in enumerate(runs_db):
                if r.run_id == run_id:
                    runs_db[i] = _run(
                        run_id, age_seconds=5 * 24 * 3600, status=RunStatus.INTERRUPTED
                    )

    reaper = RunReaper(
        recorder=cast(Any, FakeRecorder()), store=cast(Any, FakeStore()), clock=lambda: NOW
    )
    closed = await reaper.reap(limit=2)

    assert closed == ("run-0", "run-1", "run-2", "run-3", "run-4")
    assert interrupted == ["run-0", "run-1", "run-2", "run-3", "run-4"]
