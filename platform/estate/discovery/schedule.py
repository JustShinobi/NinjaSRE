"""Turning a sweep into work the scheduler already knows how to divide.

FR-011 asks that concurrent discovery across replicas converge to one result,
and that the mechanism be the one the scheduler already uses. So there is no
locking here and no coordination service: a sweep is a *scheduled job*, and a
worker claims it with the same lease-based claiming that stops two replicas
running one investigation.

That gives two layers of protection, which is what the scheduler's own module
says about the same problem and is worth repeating because the failure it
prevents is worse here.

**The claim** hands each due sweep to exactly one worker. A second replica
asking at the same instant divides the batch and never receives a sweep the
first one got. The claim is a lease, so a worker that died releases its sweep
after ``DISCOVERY_LEASE_SECONDS`` rather than blocking it until a human notices.

**Derived identity** catches the case where the claim was wrong anyway — an
expired lease, a partitioned replica. Resource identifiers, sweep identifiers
and health-transition keys are all derived from what was observed rather than
generated, so two replicas that both swept the same source at the same instant
write *the same rows*. The estate converges instead of doubling.

The lease is longer than ``MAX_SWEEP_SECONDS`` on purpose: a sweep that runs to
its own time bound must never be reclaimed underneath itself, or the two layers
above would be tested against each other every time a provider was slow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.estate import DISCOVERY_LEASE_SECONDS, ESTATE_DISCOVERY_JOB_KIND
from platform.estate.discovery.port import DiscoveryDeclaration, DiscoveryMode
from platform.persistence.ports.schedule_store import JobClaim, JobDispatcher, ScheduledJob
from platform.scheduler.claiming import JobClaimer

#: Where the source's name lives inside a claimed job's payload. One constant,
#: because the job is written by one module and read by another and a typo
#: between them is a sweep that silently never runs.
PAYLOAD_SOURCE = "source"

#: Where the mode lives. Absent means full, which is the safe default: a sweep
#: that ran full when it could have run incremental costs provider calls, and
#: one that ran incremental when it should have run full concludes nothing.
PAYLOAD_MODE = "mode"


def job_id_for(source: str) -> str:
    """Return the scheduled job that sweeps ``source``.

    Derived from the source rather than generated, so re-registering an
    integration updates its schedule instead of adding a second one that sweeps
    the same provider twice as often.
    """
    return f"{ESTATE_DISCOVERY_JOB_KIND}:{source}"


def sweep_job(
    declaration: DiscoveryDeclaration,
    *,
    next_run_at: datetime,
    source: str = "",
    mode: DiscoveryMode = DiscoveryMode.FULL,
) -> ScheduledJob:
    """Return the recurring job that sweeps one source.

    The schedule is expressed in the declaration's interval rather than in cron,
    because "every fifteen minutes" is what an integration means and a cron
    expression would make every integration author choose a minute of the hour
    — after which eighty integrations all sweep at ``:00``.
    """
    integration = source or declaration.integration
    return ScheduledJob(
        job_id=job_id_for(integration),
        name=f"Discover {integration} resources",
        kind=ESTATE_DISCOVERY_JOB_KIND,
        schedule=f"every {declaration.interval_seconds}s",
        next_run_at=next_run_at,
        payload={PAYLOAD_SOURCE: integration, PAYLOAD_MODE: mode.value},
    )


def next_run_after(declaration: DiscoveryDeclaration, *, now: datetime) -> datetime:
    """Return when this source is due again after a sweep at ``now``."""
    return now + timedelta(seconds=declaration.interval_seconds)


def source_of(claim: JobClaim) -> str:
    """Return the source a claimed sweep is for, or ``""`` if the claim is not one."""
    return str(claim.payload.get(PAYLOAD_SOURCE, ""))


def mode_of(claim: JobClaim) -> DiscoveryMode:
    """Return the mode a claimed sweep asks for, defaulting to full.

    Defaulting to full rather than raising on an unrecognised value: a payload
    somebody hand-edited should cost provider calls, not a sweep that never
    runs and an estate that quietly goes stale.
    """
    raw = str(claim.payload.get(PAYLOAD_MODE, DiscoveryMode.FULL.value))
    return (
        DiscoveryMode.INCREMENTAL if raw == DiscoveryMode.INCREMENTAL.value else DiscoveryMode.FULL
    )


@dataclass(frozen=True, slots=True)
class DiscoveryClaiming:
    """A worker's view of claiming sweeps, over the scheduler's own claimer.

    A thin wrapper rather than a second mechanism. Everything it adds is the
    discovery lease length and the filter that keeps a discovery worker from
    claiming somebody else's job — which is the whole of what makes this
    "reusing the scheduler" rather than "resembling it".
    """

    claimer: JobClaimer

    @classmethod
    def for_worker(cls, dispatcher: JobDispatcher, worker_id: str) -> DiscoveryClaiming:
        """Return claiming for ``worker_id``, with the discovery lease length."""
        return cls(
            claimer=JobClaimer(
                dispatcher=dispatcher,
                worker_id=worker_id,
                lease_seconds=DISCOVERY_LEASE_SECONDS,
            )
        )

    async def claim(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Return the discovery sweeps due at ``now`` that no other worker has."""
        claims = await self.claimer.claim_due(now=now)
        return tuple(claim for claim in claims if source_of(claim))


__all__ = [
    "PAYLOAD_MODE",
    "PAYLOAD_SOURCE",
    "DiscoveryClaiming",
    "job_id_for",
    "mode_of",
    "next_run_after",
    "source_of",
    "sweep_job",
]
