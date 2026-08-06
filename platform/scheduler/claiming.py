"""Deciding which replica runs a due job, without a lock service.

The property this delivers is that a job due at one instant produces exactly one
run across every replica of the deployment, and it delivers it with a unique
constraint rather than with etcd, Redis, or ZooKeeper. Adding a second stateful
service to a single-database deployment is a real cost, and a unique key gives
the same guarantee for nothing.

There are two layers, and both are load-bearing.

**The claim.** ``JobDispatcher.claim_due`` hands each due job to one caller and
no other; a second replica asking at the same instant divides the batch and
never receives a job the first one got. A claim is a *lease*: it expires. A lock
held by a process that died needs a human to clear it, and it will be a human
who is already busy — which is precisely wrong for a nightly disaster-recovery
validation.

**The run id.** The executor derives it from ``(job_id, fire_time)``, and
starting a run refuses a duplicate id. So even if a lease expired mid-execution
and another replica claimed the same firing, the second one cannot create a
second run record for it. The claim stops the common case cheaply; the run id
stops the case where the claim was wrong.

Heartbeating is what keeps an executing worker's lease alive. It runs as a task
beside the work rather than between steps of it, because a long capability call
is exactly when a lease would otherwise lapse — and a lapse mid-execution means
another replica starts the same investigation while the first is still in it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from config.constants.persistence import JOB_CLAIM_LEASE_SECONDS, MAX_JOB_CLAIM_BATCH
from config.constants.runs import SCHEDULER_HEARTBEAT_SECONDS
from platform.observability.logging import get_logger
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.schedule_store import JobClaim, JobDispatcher, JobOutcome

logger = get_logger(__name__)


class ClaimLost(RuntimeError):
    """A worker's lease expired and the job was reclaimed by somebody else.

    The signal to stop. Something else is now doing this job, and continuing
    would mean two replicas running one investigation — which is the exact thing
    the lease exists to prevent, arrived at from the other direction.
    """

    def __init__(self, claim_id: str, job_id: str) -> None:
        super().__init__(
            f"The lease on job {job_id} (claim {claim_id}) expired and was reclaimed. "
            "Stop: another worker is running it."
        )
        self.claim_id = claim_id
        self.job_id = job_id


def fire_key(job_id: str, fire_time: datetime) -> str:
    """Return the run id one firing of one job produces.

    Deterministic, and that is the whole point. Two replicas that both decided
    this firing was theirs derive the same id, and the second ``start_run``
    fails on a duplicate rather than producing a second investigation. The
    instant is normalised to UTC first, so two replicas in different zones agree.
    """
    return f"{job_id}@{fire_time.astimezone(UTC).isoformat()}"


@dataclass(slots=True)
class JobClaimer:
    """One worker's view of claiming, heartbeating, and releasing.

    Holds a dispatcher rather than a gateway, so a claimer is inside its
    caller's system unit of work for the claim itself. The heartbeat is not —
    renewing a lease has to happen while the work is in flight, which is after
    the claiming transaction has committed and released its connection.
    """

    dispatcher: JobDispatcher
    worker_id: str
    lease_seconds: float = JOB_CLAIM_LEASE_SECONDS

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int = MAX_JOB_CLAIM_BATCH,
    ) -> tuple[JobClaim, ...]:
        """Claim the jobs due at ``now`` that no other worker has."""
        claims = await self.dispatcher.claim_due(
            now=now, worker_id=self.worker_id, lease_seconds=self.lease_seconds, limit=limit
        )
        if claims:
            logger.info(
                "scheduler.claimed",
                worker_id=self.worker_id,
                jobs=[claim.job_id for claim in claims],
            )
        return claims

    async def heartbeat(self, claim: JobClaim, *, now: datetime) -> JobClaim:
        """Renew ``claim``'s lease, or raise ``ClaimLost`` if it has gone."""
        try:
            return await self.dispatcher.heartbeat(claim.claim_id, now=now)
        except RecordNotFound as reclaimed:
            raise ClaimLost(claim.claim_id, claim.job_id) from reclaimed

    async def release(
        self,
        claim: JobClaim,
        *,
        outcome: JobOutcome,
        completed_at: datetime,
        next_run_at: datetime | None,
    ) -> None:
        """Release ``claim``, record the outcome, and set the next due time.

        A release for a claim that already expired is not an error here. The
        worker did the work; something else may since have decided it did not,
        and the job's own schedule is what the reaper left alone for exactly
        that case.
        """
        try:
            await self.dispatcher.release(
                claim.claim_id,
                outcome=outcome,
                completed_at=completed_at,
                next_run_at=next_run_at,
            )
        except RecordNotFound:
            logger.warning(
                "scheduler.release_after_expiry",
                worker_id=self.worker_id,
                job_id=claim.job_id,
                claim_id=claim.claim_id,
            )


@contextlib.asynccontextmanager
async def heartbeating(
    claimer: JobClaimer,
    claim: JobClaim,
    *,
    interval_seconds: float = SCHEDULER_HEARTBEAT_SECONDS,
) -> AsyncIterator[asyncio.Task[None]]:
    """Renew ``claim``'s lease in the background for the length of the block.

    Yields the task so a caller can inspect it. Cancelled on the way out
    whatever happened inside, because a heartbeat outliving its work would keep
    a lease alive for a job nobody is running — which is a lock again, with
    extra steps.
    """

    async def renew() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await claimer.heartbeat(claim, now=datetime.now(UTC))

    task = asyncio.create_task(renew(), name=f"heartbeat-{claim.job_id}")
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


__all__ = ["ClaimLost", "JobClaimer", "fire_key", "heartbeating"]
