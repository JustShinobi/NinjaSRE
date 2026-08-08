"""Turning the tick into work the scheduler already knows how to divide.

FR-010 asks that concurrent evaluation across replicas use the scheduler's
existing lease-based claiming, and this is the whole of the mechanism: the tick
is a *scheduled job*, and a worker claims it exactly as it claims a nightly
investigation or a discovery sweep. There is no lock service and no coordination
protocol of our own.

Two layers protect the property, and the second is why the first can be a lease
rather than a lock.

**The claim** hands each due tick to one worker. A second replica asking at the
same instant receives nothing, and a worker that died releases its tick after
``OBSERVATION_LEASE_SECONDS`` rather than blocking evaluation until a human
notices.

**Statelessness** catches the case where the claim was wrong anyway — an expired
lease, a partitioned replica. Evaluation remembers nothing between ticks, and a
finding's correlation key is derived from the detector and its subjects, so two
replicas that both evaluated the same estate at the same instant reach the same
verdicts and their incidents land on each other rather than beside each other.
The estate converges instead of doubling.

The lease is longer than the tick's own budget on purpose: a tick that runs to
its declared ceiling must never be reclaimed underneath itself, or the two
layers above would be tested against each other every time the estate grew.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.observation import (
    DEFAULT_TICK_INTERVAL_SECONDS,
    MIN_TICK_INTERVAL_SECONDS,
    OBSERVATION_LEASE_SECONDS,
    OBSERVATION_TICK_JOB_KIND,
)
from platform.observation.errors import ObservationBoundExceeded
from platform.persistence.ports.schedule_store import JobClaim, JobDispatcher, ScheduledJob
from platform.scheduler.claiming import JobClaimer

#: Where the tick's interval lives inside a claimed job's payload. One constant,
#: because the job is written by one module and read by another and a typo
#: between them is a deployment that quietly stops watching.
PAYLOAD_INTERVAL = "interval_seconds"

#: The scheduled job every deployment has exactly one of. Derived rather than
#: generated, so re-registering the tick updates its schedule instead of adding
#: a second one that evaluates the estate twice as often.
TICK_JOB_ID = f"{OBSERVATION_TICK_JOB_KIND}:estate"


def tick_job(
    *,
    next_run_at: datetime,
    interval_seconds: int = DEFAULT_TICK_INTERVAL_SECONDS,
) -> ScheduledJob:
    """Return the recurring job that evaluates the estate.

    Raises ``ObservationBoundExceeded`` below the interval floor. A tick shorter
    than the floor overlaps itself at estate scale, and an evaluation that
    started before the last one finished is two replicas of one worker with none
    of the coordination.
    """
    if interval_seconds < MIN_TICK_INTERVAL_SECONDS:
        raise ObservationBoundExceeded(
            parameter="observation tick interval",
            requested=interval_seconds,
            limit=MIN_TICK_INTERVAL_SECONDS,
            constant="MIN_TICK_INTERVAL_SECONDS",
        )
    return ScheduledJob(
        job_id=TICK_JOB_ID,
        name="Evaluate the estate's detectors",
        kind=OBSERVATION_TICK_JOB_KIND,
        schedule=f"every {interval_seconds}s",
        next_run_at=next_run_at,
        payload={PAYLOAD_INTERVAL: interval_seconds},
    )


def interval_of(claim: JobClaim) -> int:
    """Return the interval a claimed tick declares, or the default.

    Defaulting rather than raising on a payload somebody hand-edited: a bad
    number should cost an oddly-timed tick, not a deployment that stops watching
    because its job payload has a typo in it.
    """
    raw = claim.payload.get(PAYLOAD_INTERVAL, DEFAULT_TICK_INTERVAL_SECONDS)
    try:
        interval = int(str(raw))
    except (TypeError, ValueError):
        return DEFAULT_TICK_INTERVAL_SECONDS
    return max(interval, MIN_TICK_INTERVAL_SECONDS)


def next_tick_after(claim: JobClaim, *, now: datetime) -> datetime:
    """Return when the estate is due to be evaluated again."""
    return now + timedelta(seconds=interval_of(claim))


@dataclass(frozen=True, slots=True)
class ObservationClaiming:
    """A worker's view of claiming ticks, over the scheduler's own claimer.

    A thin wrapper rather than a second mechanism. Everything it adds is the
    observation lease length and the filter that keeps an observation worker
    from claiming somebody else's job — which is what makes this "reusing the
    scheduler" rather than "resembling it".
    """

    claimer: JobClaimer

    @classmethod
    def for_worker(cls, dispatcher: JobDispatcher, worker_id: str) -> ObservationClaiming:
        """Return claiming for ``worker_id``, with the observation lease length."""
        return cls(
            claimer=JobClaimer(
                dispatcher=dispatcher,
                worker_id=worker_id,
                lease_seconds=OBSERVATION_LEASE_SECONDS,
            )
        )

    async def claim(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Return the evaluation ticks due at ``now`` that no other worker has."""
        claims = await self.claimer.claim_due(now=now)
        return tuple(claim for claim in claims if claim.job_id == TICK_JOB_ID)


__all__ = [
    "PAYLOAD_INTERVAL",
    "TICK_JOB_ID",
    "ObservationClaiming",
    "interval_of",
    "next_tick_after",
    "tick_job",
]
