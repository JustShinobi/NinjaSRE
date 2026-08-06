"""What a recurring investigation is, and what a claim on one carries.

The store's ``ScheduledJob`` is deliberately generic — an id, a kind, a schedule
string, a payload, a due time — because the same table holds a knowledge sync
and a topology discovery as well as an investigation. ``Schedule`` is the
investigation-shaped reading of one, and the mapping between them is here rather
than spread across the executor and the service so that "what does the payload
hold" has one answer.

Two fields are worth arguing about.

**A schedule carries a principal.** Not because anything technical needs one,
but because a run has to be attributable and "the scheduler" is not a person. An
approval raised inside a scheduled run attributes to this principal, which is
what makes a schedule *not* a way to act without anybody being responsible for
it. Article III: a schedule is not an autonomy bypass.

**A disabled schedule says why it was disabled.** An operator's decision, a
deleted team, and an expression that stopped parsing are three different states
that a boolean collapses into one — and the second is the one where somebody
needs to be told rather than left to discover a job that quietly stopped.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from config.constants.runs import DEFAULT_SCHEDULE_TIMEZONE
from platform.persistence.ports.schedule_store import JobOutcome, ScheduledJob

#: The ``kind`` every schedule this package owns is stored under. The store
#: holds other kinds — a knowledge sync, a topology discovery — and filtering on
#: this is what keeps one scheduler from executing another's work.
INVESTIGATION_JOB_KIND = "investigation"

#: Keys inside a stored job's payload. Named for the same reason the run
#: metadata keys are: two readers of one dictionary is two chances to disagree.
_TEAM = "team_node_id"
_PRINCIPAL = "principal_id"
_OBJECTIVE = "objective"
_TIMEZONE = "timezone"
_MISFIRE = "misfire"
_DISABLED = "disabled_reason"
_CONTEXT = "context"


class MisfirePolicy(StrEnum):
    """What to do about firings that came due while nothing was running.

    Three answers because there are three genuinely different jobs. A health
    sweep wants ``SKIP`` — yesterday's answer is worthless. A nightly report
    wants ``RUN_ONCE`` — one is owed, not seven. A per-firing task that
    accumulates wants ``RUN_ALL``, bounded, because the alternative is a
    deployment that comes back from a week's outage and starts two thousand
    investigations at once.
    """

    SKIP = "skip"
    RUN_ONCE = "run_once"
    RUN_ALL = "run_all"


class DisabledReason(StrEnum):
    """Why a schedule is not running."""

    OPERATOR = "operator"
    TEAM_DELETED = "team_deleted"
    INVALID_SCHEDULE = "invalid_schedule"


@dataclass(frozen=True, slots=True)
class Schedule:
    """One recurring investigation, as this package reads it."""

    job_id: str
    name: str
    team_node_id: str
    principal_id: str
    cron: str
    objective: str = ""
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    misfire: MisfirePolicy = MisfirePolicy.RUN_ONCE
    enabled: bool = True
    disabled_reason: DisabledReason | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_outcome: JobOutcome | None = None
    created_at: datetime | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_job(self) -> ScheduledJob:
        """Return the store's record of this schedule."""
        return ScheduledJob(
            job_id=self.job_id,
            name=self.name,
            kind=INVESTIGATION_JOB_KIND,
            schedule=self.cron,
            next_run_at=self.next_run_at,
            enabled=self.enabled,
            last_run_at=self.last_run_at,
            last_outcome=self.last_outcome,
            created_at=self.created_at,
            payload={
                _TEAM: self.team_node_id,
                _PRINCIPAL: self.principal_id,
                _OBJECTIVE: self.objective,
                _TIMEZONE: self.timezone,
                _MISFIRE: self.misfire.value,
                _DISABLED: None if self.disabled_reason is None else self.disabled_reason.value,
                _CONTEXT: dict(self.context),
            },
        )

    @classmethod
    def of(cls, job: ScheduledJob) -> Schedule:
        """Return the schedule ``job`` stores.

        Tolerant of a payload written before a field existed, because a stored
        job predating a change must not become unreadable — a schedule that
        stopped loading is a schedule that stopped running, silently.
        """
        payload = job.payload
        return cls(
            job_id=job.job_id,
            name=job.name,
            team_node_id=str(payload.get(_TEAM, "")),
            principal_id=str(payload.get(_PRINCIPAL, "")),
            cron=job.schedule,
            objective=str(payload.get(_OBJECTIVE, "")),
            timezone=str(payload.get(_TIMEZONE, DEFAULT_SCHEDULE_TIMEZONE)),
            misfire=_policy(payload.get(_MISFIRE)),
            enabled=job.enabled,
            disabled_reason=_reason(payload.get(_DISABLED)),
            next_run_at=job.next_run_at,
            last_run_at=job.last_run_at,
            last_outcome=job.last_outcome,
            created_at=job.created_at,
            context=dict(payload.get(_CONTEXT) or {}),
        )

    def disabled(self, reason: DisabledReason) -> Schedule:
        """Return this schedule stopped, with the reason recorded.

        Unscheduled as well as disabled: leaving ``next_run_at`` in the past on
        a disabled job means re-enabling it fires immediately for a time that
        has gone, which is a misfire nobody asked for.
        """
        return replace(self, enabled=False, disabled_reason=reason, next_run_at=None)

    def scheduled_for(self, moment: datetime | None) -> Schedule:
        """Return this schedule due at ``moment``."""
        return replace(self, next_run_at=moment)


def _policy(value: Any) -> MisfirePolicy:
    """Return the misfire policy ``value`` names, defaulting to running once."""
    try:
        return MisfirePolicy(value)
    except ValueError:
        return MisfirePolicy.RUN_ONCE


def _reason(value: Any) -> DisabledReason | None:
    """Return the disabled reason ``value`` names, or ``None``."""
    if value is None:
        return None
    try:
        return DisabledReason(value)
    except ValueError:
        return DisabledReason.OPERATOR


__all__ = [
    "INVESTIGATION_JOB_KIND",
    "DisabledReason",
    "MisfirePolicy",
    "Schedule",
]
