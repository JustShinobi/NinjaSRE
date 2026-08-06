"""What to do about the firings that happened while nothing was listening.

A deployment restarts, or is down for a weekend, and comes back to a schedule
whose fire time was six hours ago. Three reasonable answers, and the reason all
three exist is that they belong to genuinely different jobs rather than to
different tastes:

- a **health sweep** wants ``SKIP``, because yesterday's answer is worthless and
  running it now tells you about a system that has already changed;
- a **nightly report** wants ``RUN_ONCE``, because one report is owed and seven
  identical ones are noise;
- an accumulating task wants ``RUN_ALL``, and even it wants a bound, because a
  deployment returning from a week's outage must not start two thousand
  investigations in the same minute.

The grace period is what separates "the system was busy" from "the system was
down". A firing a minute late is not a misfire; the queue was full, the policy
should not apply, and the run happens. That distinction is the reason a schedule
with a ``SKIP`` policy still runs when a concurrency limit delayed it by ninety
seconds — which is the behaviour an operator expects and the one a naive
implementation gets wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.runs import MAX_MISFIRE_CATCH_UP_RUNS, SCHEDULER_MISFIRE_GRACE_SECONDS
from platform.scheduler.cron import CronError, CronExpression
from platform.scheduler.models import MisfirePolicy, Schedule


@dataclass(frozen=True, slots=True)
class Recovery:
    """Which firings to run now, and what the schedule's next due time becomes."""

    fire_times: tuple[datetime, ...] = ()
    next_run_at: datetime | None = None
    skipped: int = 0
    capped: bool = False

    @property
    def runs(self) -> int:
        """Return how many runs this recovery will produce."""
        return len(self.fire_times)


def resolve(
    schedule: Schedule,
    *,
    now: datetime,
    grace_seconds: float = SCHEDULER_MISFIRE_GRACE_SECONDS,
    limit: int = MAX_MISFIRE_CATCH_UP_RUNS,
) -> Recovery:
    """Return what a due-but-late ``schedule`` should do at ``now``.

    A schedule with no due time gets nothing to run and nothing to reschedule:
    it is either brand new, disabled, or a one-shot that has already fired, and
    inventing a firing for it would be inventing work.
    """
    due = schedule.next_run_at
    if due is None or due > now:
        return Recovery(next_run_at=due)

    expression = CronExpression.parse(schedule.cron, timezone=schedule.timezone)
    within_grace = (now - due) <= timedelta(seconds=grace_seconds)

    # Late but not *very* late: the system was busy, not absent. Run it.
    if within_grace:
        return Recovery(fire_times=(due,), next_run_at=_after(expression, due))

    missed = _missed(expression, due, now, limit=limit)

    match schedule.misfire:
        case MisfirePolicy.SKIP:
            return Recovery(next_run_at=_after(expression, now), skipped=len(missed))
        case MisfirePolicy.RUN_ONCE:
            # The most recent, not the oldest: a report catching up should
            # describe the world as it is, not as it was six hours ago.
            latest = missed[-1] if missed else due
            return Recovery(
                fire_times=(latest,),
                next_run_at=_after(expression, latest),
                skipped=max(len(missed) - 1, 0),
            )
        case MisfirePolicy.RUN_ALL:
            capped = missed[:limit]
            return Recovery(
                fire_times=tuple(capped),
                next_run_at=_after(expression, capped[-1] if capped else due),
                skipped=len(missed) - len(capped),
                capped=len(missed) > limit,
            )


def _missed(
    expression: CronExpression, due: datetime, now: datetime, *, limit: int
) -> Sequence[datetime]:
    """Return the fire times from ``due`` up to ``now``, bounded.

    Bounded by ``limit + 1`` rather than by ``limit``: the extra one is what
    lets the caller tell "exactly at the cap" from "more than the cap", which is
    the difference between a clean catch-up and one that dropped work.
    """
    times = [due]
    cursor = due
    while len(times) <= limit:
        try:
            following = expression.next_after(cursor).at
        except CronError:  # pragma: no cover — the expression parsed already
            break
        if following > now:
            break
        times.append(following)
        cursor = following
    return times


def _after(expression: CronExpression, moment: datetime) -> datetime | None:
    """Return the firing after ``moment``, or ``None`` if there is not one."""
    try:
        return expression.next_after(moment).at
    except CronError:
        # An expression whose remaining firings have run out. The job becomes
        # unscheduled rather than disabled: it did what it was configured to do.
        return None


__all__ = ["Recovery", "resolve"]
