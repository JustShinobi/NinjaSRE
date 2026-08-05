"""Recurring work, and the claim that stops two workers from doing it twice.

Scheduling splits across the tenant boundary in a way most of this package does
not, and the split is the interesting part.

Defining a job is tenant work: an organisation decides that its nightly
knowledge sync runs at 02:00, and nothing outside that organisation has any
business knowing. ``ScheduleStore`` is therefore an ordinary tenant-scoped port.

Running one is not. A worker process serves every tenant, wakes up, and asks
what is due — a question that cannot be asked from inside a tenant without
asking it once per tenant, which is both slower and racier. ``JobDispatcher``
lives on the system unit of work for exactly that reason, and it is the reason
``JobClaim`` carries an ``org_id`` when nothing else in this package does: a
claim is the record that hands work back across the boundary.

Claims are leases, not locks. A worker that dies holding one blocks its job for
``JOB_CLAIM_LEASE_SECONDS`` and no longer, because a lock that outlives its
holder needs a human to clear it, and it will be a human who is already busy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.persistence import JOB_CLAIM_LEASE_SECONDS, MAX_JOB_CLAIM_BATCH


class JobOutcome(StrEnum):
    """How one run of a job ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """One piece of recurring work, and when it next comes due.

    ``next_run_at`` is stored rather than computed from ``schedule`` at query
    time. Evaluating a cron expression per row is what turns "what is due" from
    an index lookup into a scan of every job in the deployment.

    ``None`` means unscheduled: defined, possibly enabled, and not coming due.
    That is what a one-shot job looks like after it has run, and it is a
    different state from disabled — which is an operator's decision rather than
    a consequence of the job having finished.
    """

    job_id: str
    name: str
    kind: str
    schedule: str
    next_run_at: datetime | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run_at: datetime | None = None
    last_outcome: JobOutcome | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobClaim:
    """One worker's lease on one job.

    Carries ``org_id`` because it crosses the tenant boundary: the dispatcher
    claimed it without a scope, and the worker needs one to open a unit of work
    and do the job.
    """

    claim_id: str
    job_id: str
    org_id: str
    worker_id: str
    claimed_at: datetime
    lease_expires_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ScheduleStore(Protocol):
    """Job definitions, within one tenant."""

    async def upsert_job(self, job: ScheduledJob) -> ScheduledJob:
        """Store ``job``, replacing any earlier definition, and return it."""

    async def get_job(self, job_id: str) -> ScheduledJob | None:
        """Return the job with ``job_id``, or ``None``."""

    async def list_jobs(
        self,
        *,
        kind: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> tuple[ScheduledJob, ...]:
        """Return matching jobs, soonest-due first, unscheduled ones last."""

    async def set_enabled(self, job_id: str, *, enabled: bool) -> ScheduledJob:
        """Enable or disable ``job_id`` and return it.

        Disabling rather than deleting is the safe way to stop a job, and
        keeping both operations means an operator does not have to choose
        between stopping it and losing its definition.
        """

    async def delete_job(self, job_id: str) -> bool:
        """Delete ``job_id`` and return whether it existed."""


@runtime_checkable
class JobDispatcher(Protocol):
    """Claiming and releasing due work, across every tenant.

    Reached only through the system unit of work. Four operations, each of
    which genuinely cannot know its tenant in advance.
    """

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: float = JOB_CLAIM_LEASE_SECONDS,
        limit: int = MAX_JOB_CLAIM_BATCH,
    ) -> tuple[JobClaim, ...]:
        """Claim up to ``limit`` jobs due at ``now``, and return the claims.

        Claiming is atomic per job: two workers calling this concurrently
        divide the due jobs between them and never both receive one. Disabled
        jobs are never returned. Raises ``BoundExceeded`` above
        ``MAX_JOB_CLAIM_BATCH`` — a worker that claimed the entire backlog
        would leave every other worker idle and then drop the lot when it
        restarted.
        """

    async def heartbeat(self, claim_id: str, *, now: datetime) -> JobClaim:
        """Extend a claim's lease and return it.

        Raises ``RecordNotFound`` when the lease has already expired and been
        reclaimed — which is the signal for the worker to stop, because
        something else is now doing this job.
        """

    async def release(
        self,
        claim_id: str,
        *,
        outcome: JobOutcome,
        completed_at: datetime,
        next_run_at: datetime | None = None,
    ) -> None:
        """Release a claim, record the outcome, and schedule the next run.

        ``next_run_at`` of ``None`` leaves the job unscheduled, which is what a
        one-shot job wants.
        """

    async def expire_leases(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Release every lease that has run out, and return what was released.

        Records those jobs as ``ABANDONED`` and leaves their schedule exactly
        where it was, so the next worker to ask finds them due. That is the
        entire purpose of a lease rather than a lock.

        ``ABANDONED`` rather than ``FAILED``: a job whose worker vanished did
        not fail — nobody knows whether it ran — and recording it as a failure
        would put a false entry in the operator's history of it.
        """


__all__ = [
    "JobClaim",
    "JobDispatcher",
    "JobOutcome",
    "ScheduleStore",
    "ScheduledJob",
]
