"""Scheduled jobs and the cross-tenant dispatcher over PostgreSQL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants.persistence import JOB_CLAIM_LEASE_SECONDS, MAX_JOB_CLAIM_BATCH
from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.ports.schedule_store import JobClaim, JobOutcome, ScheduledJob
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    check_limit,
    translating,
    utc_now,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _to_job(row: models.ScheduledJob) -> ScheduledJob:
    return ScheduledJob(
        job_id=row.job_id,
        name=row.name,
        kind=row.kind,
        schedule=row.schedule,
        next_run_at=as_utc(row.next_run_at),
        payload=dict(row.payload),
        enabled=row.enabled,
        last_run_at=as_utc(row.last_run_at),
        last_outcome=JobOutcome(row.last_outcome) if row.last_outcome else None,
        created_at=as_utc(row.created_at),
    )


def _to_claim(row: models.JobClaim) -> JobClaim:
    return JobClaim(
        claim_id=row.claim_id,
        job_id=row.job_id,
        org_id=row.org_id,
        worker_id=row.worker_id,
        claimed_at=as_utc(row.claimed_at) or row.claimed_at,
        lease_expires_at=as_utc(row.lease_expires_at) or row.lease_expires_at,
        payload=dict(row.payload),
    )


@dataclass(slots=True)
class PostgresScheduleStore(TenantBound):
    """Job definitions for one organisation."""

    async def upsert_job(self, job: ScheduledJob) -> ScheduledJob:
        """Store ``job``, replacing any earlier definition, and return it."""
        row = await self.session.get(models.ScheduledJob, (self.org_id, job.job_id))
        if row is None:
            row = models.ScheduledJob(org_id=self.org_id, job_id=job.job_id)
            self.session.add(row)
            row.created_at = job.created_at or utc_now()
        elif job.created_at is not None:
            row.created_at = job.created_at

        row.name = job.name
        row.kind = job.kind
        row.schedule = job.schedule
        row.next_run_at = job.next_run_at
        row.payload = check_payload(job.payload, kind="scheduled job payload")
        row.enabled = job.enabled
        row.last_run_at = job.last_run_at
        row.last_outcome = job.last_outcome.value if job.last_outcome else None

        await self.session.flush()
        return _to_job(row)

    async def get_job(self, job_id: str) -> ScheduledJob | None:
        """Return the job with ``job_id``, or ``None``."""
        row = await self.session.get(models.ScheduledJob, (self.org_id, job_id))
        return _to_job(row) if row is not None else None

    async def list_jobs(
        self,
        *,
        kind: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> tuple[ScheduledJob, ...]:
        """Return matching jobs, soonest-due first, unscheduled ones last."""
        check_limit(limit)
        statement = (
            select(models.ScheduledJob)
            .where(models.ScheduledJob.org_id == self.org_id)
            # NULLS LAST rather than a sentinel date: an unscheduled job is not
            # due in the year 9999, it is not due.
            .order_by(
                models.ScheduledJob.next_run_at.asc().nullslast(),
                models.ScheduledJob.job_id.asc(),
            )
            .limit(limit)
        )
        if kind is not None:
            statement = statement.where(models.ScheduledJob.kind == kind)
        if enabled_only:
            statement = statement.where(models.ScheduledJob.enabled.is_(True))

        rows = await self.session.scalars(statement)
        return tuple(_to_job(row) for row in rows)

    async def set_enabled(self, job_id: str, *, enabled: bool) -> ScheduledJob:
        """Enable or disable ``job_id`` and return it."""
        row = await self.session.get(models.ScheduledJob, (self.org_id, job_id))
        if row is None:
            raise RecordNotFound(kind="scheduled job", identifier=job_id)
        row.enabled = enabled
        await self.session.flush()
        return _to_job(row)

    async def delete_job(self, job_id: str) -> bool:
        """Delete ``job_id`` and return whether it existed."""
        row = await self.session.get(models.ScheduledJob, (self.org_id, job_id))
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


@dataclass(slots=True)
class PostgresJobDispatcher:
    """Claiming and releasing due work, across every organisation."""

    session: AsyncSession

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: float = JOB_CLAIM_LEASE_SECONDS,
        limit: int = MAX_JOB_CLAIM_BATCH,
    ) -> tuple[JobClaim, ...]:
        """Claim up to ``limit`` jobs due at ``now``, and return the claims.

        ``FOR UPDATE SKIP LOCKED`` is what makes two workers polling at the same
        instant divide the backlog instead of colliding on it: each takes the
        rows the other has not locked, and neither waits. The unique constraint
        on ``(org_id, job_id)`` in ``job_claims`` is the backstop — if the lock
        were ever wrong, the second insert would fail rather than hand one job
        to two workers.
        """
        if limit > MAX_JOB_CLAIM_BATCH:
            raise BoundExceeded(
                parameter="limit",
                requested=limit,
                limit=MAX_JOB_CLAIM_BATCH,
                constant="MAX_JOB_CLAIM_BATCH",
            )

        held = select(models.JobClaim.job_id, models.JobClaim.org_id).subquery()
        due = await self.session.scalars(
            select(models.ScheduledJob)
            .where(
                models.ScheduledJob.enabled.is_(True),
                models.ScheduledJob.next_run_at.is_not(None),
                models.ScheduledJob.next_run_at <= now,
                ~select(held.c.job_id)
                .where(
                    held.c.job_id == models.ScheduledJob.job_id,
                    held.c.org_id == models.ScheduledJob.org_id,
                )
                .exists(),
            )
            .order_by(
                models.ScheduledJob.next_run_at.asc(),
                models.ScheduledJob.org_id.asc(),
                models.ScheduledJob.job_id.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        claims: list[models.JobClaim] = []
        for job in due:
            claim = models.JobClaim(
                claim_id=str(uuid.uuid4()),
                org_id=job.org_id,
                job_id=job.job_id,
                worker_id=worker_id,
                claimed_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                payload=dict(job.payload),
            )
            self.session.add(claim)
            claims.append(claim)

        with translating(kind="job claim", identifier=worker_id, referenced="scheduled job"):
            await self.session.flush()
        return tuple(_to_claim(claim) for claim in claims)

    async def heartbeat(self, claim_id: str, *, now: datetime) -> JobClaim:
        """Extend a claim's lease and return it."""
        row = await self.session.get(models.JobClaim, claim_id)
        if row is None:
            raise RecordNotFound(kind="job claim", identifier=claim_id)
        row.lease_expires_at = now + timedelta(seconds=JOB_CLAIM_LEASE_SECONDS)
        await self.session.flush()
        return _to_claim(row)

    async def release(
        self,
        claim_id: str,
        *,
        outcome: JobOutcome,
        completed_at: datetime,
        next_run_at: datetime | None = None,
    ) -> None:
        """Release a claim, record the outcome, and schedule the next run."""
        row = await self.session.get(models.JobClaim, claim_id)
        if row is None:
            raise RecordNotFound(kind="job claim", identifier=claim_id)

        await self._record_outcome(
            row, outcome=outcome, at=completed_at, next_run_at=next_run_at, reschedule=True
        )
        await self.session.delete(row)
        await self.session.flush()

    async def expire_leases(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Release every lease that has run out, and return what was released."""
        rows = list(
            await self.session.scalars(
                select(models.JobClaim)
                .where(models.JobClaim.lease_expires_at <= now)
                .order_by(models.JobClaim.claimed_at.asc(), models.JobClaim.claim_id.asc())
            )
        )
        released = tuple(_to_claim(row) for row in rows)

        for row in rows:
            await self._record_outcome(
                row,
                outcome=JobOutcome.ABANDONED,
                at=now,
                next_run_at=None,
                reschedule=False,
            )
        if rows:
            await self.session.execute(
                delete(models.JobClaim).where(
                    models.JobClaim.claim_id.in_([row.claim_id for row in rows])
                )
            )
        await self.session.flush()
        return released

    async def _record_outcome(
        self,
        claim: models.JobClaim,
        *,
        outcome: JobOutcome,
        at: datetime,
        next_run_at: datetime | None,
        reschedule: bool,
    ) -> None:
        """Write a run's outcome back onto its job definition, if the job survives.

        ``reschedule`` separates a release from an expiry. A worker that
        finished decides when the job comes due again, including never. A worker
        that vanished decided nothing, so the schedule is left where it was and
        the job is due for whoever asks next — which is the entire purpose of a
        lease rather than a lock.

        A job deleted while a worker held its claim is not resurrected. The
        release still succeeds: the worker did the work and has nothing to undo.
        """
        job = await self.session.get(models.ScheduledJob, (claim.org_id, claim.job_id))
        if job is None:
            return
        job.last_run_at = at
        job.last_outcome = outcome.value
        if reschedule:
            job.next_run_at = next_run_at


__all__ = ["PostgresJobDispatcher", "PostgresScheduleStore"]
