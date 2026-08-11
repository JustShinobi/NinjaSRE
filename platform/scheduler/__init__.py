"""Running investigations on a recurring basis, exactly once across replicas.

A schedule is not an autonomy bypass. A scheduled run is gated by the same
approvals an interactive one is, attributes to the schedule's own principal, and
produces the same run, trace, episode, and report — differing only in its
trigger. Everything downstream of a run therefore has one case rather than two.

Exactly-once comes from two layers rather than a lock service: a lease claimed
per job, and a run id derived from ``(job_id, fire_time)`` that a duplicate
cannot get past. The first stops the common case cheaply, and the second is what
holds when a lease expires mid-execution.
"""

from __future__ import annotations

from platform.scheduler.claiming import ClaimLost, JobClaimer, fire_key, heartbeating
from platform.scheduler.concurrency import ConcurrencyLimits
from platform.scheduler.cron import CronError, CronExpression, FireTime
from platform.scheduler.dispatch import (
    DispatchResult,
    JobContext,
    JobKindDispatcher,
    JobRunner,
    ScheduledJobWorker,
    UnknownJobKind,
    next_due,
)
from platform.scheduler.executor import (
    EffectiveSettings,
    ExecutionResult,
    JobExecutor,
    ScheduledInvestigation,
    ScheduledRunRequest,
)
from platform.scheduler.misfire import Recovery, resolve
from platform.scheduler.models import (
    INVESTIGATION_JOB_KIND,
    DisabledReason,
    MisfirePolicy,
    Schedule,
)
from platform.scheduler.reaper import LeaseReaper, ReapReport
from platform.scheduler.service import ScheduleService

__all__ = [
    "INVESTIGATION_JOB_KIND",
    "ClaimLost",
    "ConcurrencyLimits",
    "CronError",
    "CronExpression",
    "DisabledReason",
    "DispatchResult",
    "EffectiveSettings",
    "ExecutionResult",
    "FireTime",
    "JobClaimer",
    "JobContext",
    "JobExecutor",
    "JobKindDispatcher",
    "JobRunner",
    "LeaseReaper",
    "MisfirePolicy",
    "ReapReport",
    "Recovery",
    "Schedule",
    "ScheduleService",
    "ScheduledInvestigation",
    "ScheduledJobWorker",
    "ScheduledRunRequest",
    "UnknownJobKind",
    "fire_key",
    "heartbeating",
    "next_due",
    "resolve",
]
