"""Managing schedules, and disabling the ones whose team went away.

The console's half of the feature. Creating a schedule validates its expression
*before* storing it and computes the first due time from it, because a schedule
that only reveals it is malformed on the night it was meant to run is one nobody
hears about until the morning after.

The deleted-team case is the one worth stating. A job whose team no longer
exists is **disabled with a recorded reason**, never silently dropped. Dropping
it loses the definition an operator wrote and gives them nothing to look at;
leaving it running is worse, because it would resolve configuration against a
node that is not in the tree. Disabled-with-a-reason is the state that can be
explained, and re-enabled if the team comes back under a new node.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from config.constants.runs import DEFAULT_SCHEDULE_TIMEZONE
from platform.observability.logging import get_logger
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.schedule_store import ScheduleStore
from platform.scheduler.cron import CronError, CronExpression
from platform.scheduler.models import (
    INVESTIGATION_JOB_KIND,
    DisabledReason,
    MisfirePolicy,
    Schedule,
)

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(slots=True)
class ScheduleService:
    """Create, read, change, and disable one tenant's schedules."""

    store: ScheduleStore
    clock: Callable[[], datetime] = _utc_now

    async def create(
        self,
        *,
        job_id: str,
        name: str,
        team_node_id: str,
        principal_id: str,
        cron: str,
        objective: str,
        timezone: str = DEFAULT_SCHEDULE_TIMEZONE,
        misfire: MisfirePolicy = MisfirePolicy.RUN_ONCE,
        enabled: bool = True,
        context: Mapping[str, Any] | None = None,
    ) -> Schedule:
        """Store a new schedule and return it, due at its first firing.

        Raises ``CronError`` before anything is written. A stored schedule that
        cannot be evaluated is a job that will never run and will never say why.
        """
        expression = CronExpression.parse(cron, timezone=timezone)
        now = self.clock()
        schedule = Schedule(
            job_id=job_id,
            name=name,
            team_node_id=team_node_id,
            principal_id=principal_id,
            cron=cron,
            objective=objective,
            timezone=timezone,
            misfire=misfire,
            enabled=enabled,
            next_run_at=expression.next_after(now).at if enabled else None,
            created_at=now,
            context=dict(context or {}),
        )
        stored = await self.store.upsert_job(schedule.to_job())
        logger.info(
            "scheduler.schedule_created",
            job_id=job_id,
            team_node_id=team_node_id,
            next_run_at=schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        )
        return Schedule.of(stored)

    async def get(self, job_id: str) -> Schedule | None:
        """Return the schedule with ``job_id``, or ``None``."""
        job = await self.store.get_job(job_id)
        return None if job is None else Schedule.of(job)

    async def list(
        self,
        *,
        team_node_id: str | None = None,
        enabled_only: bool = False,
        limit: int = MAX_QUERY_PAGE_SIZE,
    ) -> tuple[Schedule, ...]:
        """Return this tenant's schedules, soonest-due first."""
        jobs = await self.store.list_jobs(
            kind=INVESTIGATION_JOB_KIND, enabled_only=enabled_only, limit=limit
        )
        schedules = tuple(Schedule.of(job) for job in jobs)
        if team_node_id is None:
            return schedules
        return tuple(s for s in schedules if s.team_node_id == team_node_id)

    async def update_expression(
        self, job_id: str, *, cron: str, timezone: str | None = None
    ) -> Schedule:
        """Change a schedule's expression and recompute when it is next due."""
        schedule = await self._require(job_id)
        zone = timezone or schedule.timezone
        expression = CronExpression.parse(cron, timezone=zone)
        changed = replace(
            schedule,
            cron=cron,
            timezone=zone,
            next_run_at=expression.next_after(self.clock()).at if schedule.enabled else None,
        )
        return Schedule.of(await self.store.upsert_job(changed.to_job()))

    async def set_enabled(self, job_id: str, *, enabled: bool) -> Schedule:
        """Enable or disable a schedule by an operator's decision.

        Enabling recomputes the due time from now rather than restoring the one
        it had: re-enabling a schedule that has been off for a month must not
        fire immediately for a time that has long gone.
        """
        schedule = await self._require(job_id)
        if not enabled:
            changed = schedule.disabled(DisabledReason.OPERATOR)
        else:
            expression = CronExpression.parse(schedule.cron, timezone=schedule.timezone)
            changed = replace(
                schedule,
                enabled=True,
                disabled_reason=None,
                next_run_at=expression.next_after(self.clock()).at,
            )
        return Schedule.of(await self.store.upsert_job(changed.to_job()))

    async def delete(self, job_id: str) -> bool:
        """Delete a schedule and return whether it existed."""
        return await self.store.delete_job(job_id)

    async def disable_orphans(self, *, live_teams: Sequence[str]) -> tuple[Schedule, ...]:
        """Disable every schedule whose team is not in ``live_teams``.

        Returns what was disabled, so the caller can tell somebody. A job that
        vanished silently is one an operator finds by noticing a report that
        stopped arriving, which is weeks later and by accident.
        """
        known = set(live_teams)
        disabled: list[Schedule] = []
        for schedule in await self.list():
            if schedule.team_node_id in known or not schedule.enabled:
                continue
            stopped = schedule.disabled(DisabledReason.TEAM_DELETED)
            await self.store.upsert_job(stopped.to_job())
            disabled.append(stopped)
            logger.warning(
                "scheduler.schedule_disabled",
                job_id=schedule.job_id,
                team_node_id=schedule.team_node_id,
                reason=DisabledReason.TEAM_DELETED.value,
            )
        return tuple(disabled)

    async def reschedule(self, job_id: str, *, after: datetime) -> Schedule:
        """Move a schedule's due time to its first firing after ``after``.

        An expression whose firings have run out leaves the job unscheduled
        rather than disabled: a one-shot that has fired did what it was
        configured to do, and calling that a fault would be wrong.
        """
        schedule = await self._require(job_id)
        try:
            following = CronExpression.parse(schedule.cron, timezone=schedule.timezone).next_after(
                after
            )
        except CronError:
            changed = schedule.scheduled_for(None)
        else:
            changed = schedule.scheduled_for(following.at)
        return Schedule.of(await self.store.upsert_job(changed.to_job()))

    async def _require(self, job_id: str) -> Schedule:
        """Return the schedule with ``job_id``, or raise ``RecordNotFound``."""
        schedule = await self.get(job_id)
        if schedule is None:
            raise RecordNotFound(kind="scheduled job", identifier=job_id)
        return schedule


__all__ = ["ScheduleService"]
