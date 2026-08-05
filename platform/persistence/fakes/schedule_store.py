"""In-memory scheduled jobs and the cross-tenant dispatcher."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from config.constants.persistence import JOB_CLAIM_LEASE_SECONDS, MAX_JOB_CLAIM_BATCH
from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.fakes.state import State, TenantState, check_limit, check_payload
from platform.persistence.ports.schedule_store import JobClaim, JobOutcome, ScheduledJob

#: Sorts after any real timestamp, so an unscheduled job lands at the end of a
#: soonest-due-first listing rather than the front of it.
_UNSCHEDULED = datetime.max.replace(tzinfo=UTC)


@dataclass(slots=True)
class FakeScheduleStore:
    """Job definitions for one organisation."""

    org_id: str
    state: TenantState

    async def upsert_job(self, job: ScheduledJob) -> ScheduledJob:
        """Store ``job``, replacing any earlier definition, and return it."""
        check_payload(job.payload, kind="scheduled job payload")
        stored = job if job.created_at is not None else replace(job, created_at=datetime.now(UTC))
        self.state.jobs[job.job_id] = stored
        return stored

    async def get_job(self, job_id: str) -> ScheduledJob | None:
        """Return the job with ``job_id``, or ``None``."""
        return self.state.jobs.get(job_id)

    async def list_jobs(
        self,
        *,
        kind: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> tuple[ScheduledJob, ...]:
        """Return matching jobs, soonest-due first, unscheduled ones last."""
        check_limit(limit)
        matches = [
            job
            for job in self.state.jobs.values()
            if (kind is None or job.kind == kind) and (not enabled_only or job.enabled)
        ]
        matches.sort(key=lambda j: (j.next_run_at or _UNSCHEDULED, j.job_id))
        return tuple(matches[:limit])

    async def set_enabled(self, job_id: str, *, enabled: bool) -> ScheduledJob:
        """Enable or disable ``job_id`` and return it."""
        job = self.state.jobs.get(job_id)
        if job is None:
            raise RecordNotFound(kind="scheduled job", identifier=job_id)
        stored = replace(job, enabled=enabled)
        self.state.jobs[job_id] = stored
        return stored

    async def delete_job(self, job_id: str) -> bool:
        """Delete ``job_id`` and return whether it existed."""
        return self.state.jobs.pop(job_id, None) is not None


@dataclass(slots=True)
class FakeJobDispatcher:
    """Claiming and releasing due work, across every organisation."""

    state: State

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: float = JOB_CLAIM_LEASE_SECONDS,
        limit: int = MAX_JOB_CLAIM_BATCH,
    ) -> tuple[JobClaim, ...]:
        """Claim up to ``limit`` jobs due at ``now``, and return the claims."""
        if limit > MAX_JOB_CLAIM_BATCH:
            raise BoundExceeded(
                parameter="limit",
                requested=limit,
                limit=MAX_JOB_CLAIM_BATCH,
                constant="MAX_JOB_CLAIM_BATCH",
            )

        held = {claim.job_id for claim in self.state.claims.values()}
        due = [
            (org_id, job)
            for org_id, tenant in self.state.tenants.items()
            for job in tenant.jobs.values()
            if job.enabled
            and job.next_run_at is not None
            and job.next_run_at <= now
            and job.job_id not in held
        ]
        due.sort(key=lambda pair: (pair[1].next_run_at or _UNSCHEDULED, pair[0], pair[1].job_id))

        claims: list[JobClaim] = []
        for org_id, job in due[:limit]:
            claim = JobClaim(
                claim_id=str(uuid.uuid4()),
                job_id=job.job_id,
                org_id=org_id,
                worker_id=worker_id,
                claimed_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                payload=job.payload,
            )
            self.state.claims[claim.claim_id] = claim
            claims.append(claim)
        return tuple(claims)

    async def heartbeat(self, claim_id: str, *, now: datetime) -> JobClaim:
        """Extend a claim's lease and return it."""
        claim = self.state.claims.get(claim_id)
        if claim is None:
            raise RecordNotFound(kind="job claim", identifier=claim_id)
        extended = replace(
            claim,
            lease_expires_at=now + timedelta(seconds=JOB_CLAIM_LEASE_SECONDS),
        )
        self.state.claims[claim_id] = extended
        return extended

    async def release(
        self,
        claim_id: str,
        *,
        outcome: JobOutcome,
        completed_at: datetime,
        next_run_at: datetime | None = None,
    ) -> None:
        """Release a claim, record the outcome, and schedule the next run."""
        claim = self.state.claims.pop(claim_id, None)
        if claim is None:
            raise RecordNotFound(kind="job claim", identifier=claim_id)
        self._record_outcome(
            claim,
            outcome=outcome,
            at=completed_at,
            next_run_at=next_run_at,
            reschedule=True,
        )

    async def expire_leases(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Release every lease that has run out, and return what was released."""
        lapsed = [claim for claim in self.state.claims.values() if claim.lease_expires_at <= now]
        for claim in lapsed:
            del self.state.claims[claim.claim_id]
            self._record_outcome(
                claim,
                outcome=JobOutcome.ABANDONED,
                at=now,
                next_run_at=None,
                reschedule=False,
            )
        lapsed.sort(key=lambda c: (c.claimed_at, c.claim_id))
        return tuple(lapsed)

    def _record_outcome(
        self,
        claim: JobClaim,
        *,
        outcome: JobOutcome,
        at: datetime,
        next_run_at: datetime | None,
        reschedule: bool,
    ) -> None:
        """Write a run's outcome back onto its job definition, if the job survives.

        ``reschedule`` is what separates a release from an expiry. A worker that
        finished decides when the job comes due again, including never. A worker
        that vanished decided nothing, so the schedule is left exactly where it
        was and the job is due for whoever asks next — which is the entire
        purpose of a lease.

        A job deleted while a worker held its claim is not resurrected here.
        The release still succeeds — the worker did the work and has nothing to
        undo — and the definition stays gone, which is what the operator asked
        for.
        """
        tenant = self.state.tenants.get(claim.org_id)
        if tenant is None:
            return
        job = tenant.jobs.get(claim.job_id)
        if job is None:
            return
        tenant.jobs[claim.job_id] = replace(
            job,
            last_run_at=at,
            last_outcome=outcome,
            next_run_at=next_run_at if reschedule else job.next_run_at,
        )


__all__ = ["FakeJobDispatcher", "FakeScheduleStore"]
