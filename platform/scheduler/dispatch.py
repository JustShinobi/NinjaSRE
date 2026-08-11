"""Deciding what a claimed job *is*, and running the thing that does it.

The scheduler could already define a job, store it, decide it was due, and hand
it to exactly one replica. What it could not do was the step after: look at what
had been claimed and run it. There was one execution path, and it assumed every
job was an investigation — so three kinds that a module elsewhere knows how to
define (a document sync, a corpus pass, a discovery run) have been registerable
since the day they were written and have never executed.

That is the expensive shape of scheduling defect, because it is silent. The job
exists, the console shows it enabled, the store says it is due — and nothing
happens, for ever, until somebody notices that a corpus describes last quarter.

**A kind maps to exactly one runner.** Registering a second one for the same kind
is refused rather than replacing the first: two runners for one kind is either
the same work done twice a night or the wrong one of the two doing it, and both
are found months later.

**A kind with no runner is a failure, not a silence.** The dispatcher releases
the claim with an outcome naming the kind. Recording it as a success would put a
green run in an operator's history of a job that did nothing, which is worse than
the gap it is covering. Releasing it at all — rather than letting the lease lapse
— is what keeps a job nobody can run from also blocking the worker that claimed
it for the length of a lease, every lease, for ever.

**The job is read after the claim, not carried on it.** A ``JobClaim`` crosses
the tenant boundary with an ``org_id`` and a payload; the kind and the schedule
live on the job row. Reading them back inside the tenant's own unit of work
costs one lookup and keeps the claim the small thing it is, rather than
duplicating two fields into a second table where they can disagree.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from config.constants.runs import DEFAULT_SCHEDULE_TIMEZONE
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError
from platform.persistence.ports.schedule_store import (
    JobClaim,
    JobOutcome,
    ScheduledJob,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.scheduler.claiming import JobClaimer
from platform.scheduler.cron import CronError, CronExpression

logger = get_logger(__name__)

#: The interval vocabulary a discovery declaration writes — ``every 900s``. The
#: scheduler owns cron and nothing else writes this form by hand, but a job
#: registered from an integration's declared interval arrives in it, and a
#: dispatcher that answered "unparseable" to the only other vocabulary in the
#: tree would unschedule every sweep it ran.
_INTERVAL = re.compile(r"^every\s+(\d+)\s*s$", re.IGNORECASE)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


def next_due(job: ScheduledJob, *, after: datetime) -> datetime | None:
    """Return when ``job`` is next due after ``after``, or ``None``.

    ``None`` means unscheduled rather than disabled, which is the same answer
    ``ScheduleService.reschedule`` gives an expression whose firings have run
    out: a job that cannot say when it is next due must not be left due *now*,
    because that is a worker claiming it in a loop.
    """
    interval = _INTERVAL.match(job.schedule.strip())
    if interval is not None:
        seconds = int(interval.group(1))
        return None if seconds <= 0 else after + timedelta(seconds=seconds)
    try:
        return (
            CronExpression.parse(job.schedule, timezone=DEFAULT_SCHEDULE_TIMEZONE)
            .next_after(after)
            .at
        )
    except CronError:
        logger.warning(
            "scheduler.unschedulable_expression", job_id=job.job_id, schedule=job.schedule
        )
        return None


@dataclass(frozen=True, slots=True)
class JobContext:
    """Everything a runner is given about one claimed firing.

    Carries the job as well as the claim because a runner needs both halves: the
    claim says which tenant and holds the lease, and the job says what was
    registered. Handing over only the payload would make every runner re-derive
    its own scope from a dictionary.
    """

    claim: JobClaim
    job: ScheduledJob
    scope: TenantScope
    fire_time: datetime

    @property
    def payload(self) -> Mapping[str, Any]:
        """Return the job's payload, which is where a job's arguments live."""
        return self.job.payload

    def named(self, key: str, default: str = "") -> str:
        """Return the string the payload holds at ``key``."""
        value = self.payload.get(key, default)
        return default if value is None else str(value)


@runtime_checkable
class JobRunner(Protocol):
    """Does the work one kind of scheduled job names.

    Returns the record of what it did rather than a bare success. Every one of
    these runs unattended overnight, and "it succeeded" is not something an
    operator can act on when the question in the morning is which pages were
    refused.
    """

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Do the work ``context`` names and return the record of what happened."""


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """What one claimed firing produced."""

    job_id: str
    kind: str
    outcome: JobOutcome
    record: Mapping[str, Any] = field(default_factory=dict)
    failure: str = ""
    next_run_at: datetime | None = None

    @property
    def ran(self) -> bool:
        """Return whether a runner actually did the work."""
        return self.outcome is JobOutcome.SUCCEEDED


class UnknownJobKind(LookupError):
    """No runner is registered for a claimed job's kind.

    Raised rather than returned so a caller reaching the dispatcher directly
    cannot mistake it for an empty result. The worker turns it into a released
    claim and a recorded failure, which is what an operator reads.
    """

    def __init__(self, kind: str, known: tuple[str, ...]) -> None:
        super().__init__(
            f"No runner is registered for job kind {kind!r}. "
            f"This deployment can run: {', '.join(known) or 'nothing'}."
        )
        self.kind = kind
        self.known = known


@dataclass(slots=True)
class JobKindDispatcher:
    """Maps a job's kind to the one thing that runs it."""

    runners: dict[str, JobRunner] = field(default_factory=dict)

    def register(self, kind: str, runner: JobRunner) -> None:
        """Register ``runner`` as the one thing that runs ``kind``.

        Refuses a second registration for a kind that already has one. A
        composition root that wired two would otherwise get whichever import
        happened last, which is a choice nobody made.
        """
        if kind in self.runners:
            raise ValueError(
                f"A runner is already registered for job kind {kind!r}. "
                "Two runners for one kind is the same job running twice, or the "
                "wrong one of the two running it."
            )
        self.runners[kind] = runner

    @property
    def kinds(self) -> tuple[str, ...]:
        """Return the kinds this deployment can run, in registration order."""
        return tuple(self.runners)

    def runner_for(self, kind: str) -> JobRunner:
        """Return the runner for ``kind``, or raise ``UnknownJobKind``."""
        runner = self.runners.get(kind)
        if runner is None:
            raise UnknownJobKind(kind, self.kinds)
        return runner

    async def dispatch(self, context: JobContext) -> DispatchResult:
        """Run ``context`` through the runner its kind names.

        Never raises for a runner's own failure. A worker that let one through
        would drop the release of the claim with it, and one failed sync would
        become a job that does not exist for the length of a lease.
        """
        job = context.job
        try:
            runner = self.runner_for(job.kind)
        except UnknownJobKind as unknown:
            logger.error("scheduler.no_runner_for_kind", job_id=job.job_id, kind=job.kind)
            return DispatchResult(
                job_id=job.job_id,
                kind=job.kind,
                outcome=JobOutcome.FAILED,
                failure=str(unknown),
            )

        try:
            record = await runner.run(context)
        except Exception as failure:  # noqa: BLE001 — recorded, then reported
            logger.error(
                "scheduler.job_failed",
                job_id=job.job_id,
                kind=job.kind,
                error=type(failure).__name__,
            )
            return DispatchResult(
                job_id=job.job_id,
                kind=job.kind,
                outcome=JobOutcome.FAILED,
                failure=str(failure) or type(failure).__name__,
            )

        logger.info("scheduler.job_ran", job_id=job.job_id, kind=job.kind)
        return DispatchResult(
            job_id=job.job_id,
            kind=job.kind,
            outcome=JobOutcome.SUCCEEDED,
            record=dict(record),
        )


@dataclass(slots=True)
class ScheduledJobWorker:
    """Claims what is due, runs it by kind, and releases every claim it took.

    One tick is one pass: claim, and then for each claim read the job, dispatch
    it, and release. The release happens on every path — success, failure, an
    unrunnable kind, a job an operator deleted mid-flight — because a claim that
    is not released is a job that stops existing until its lease lapses, and a
    worker that hit the same case every tick would stop the job for good.
    """

    gateway: PersistenceGateway
    dispatcher: JobKindDispatcher
    worker_id: str = "scheduler"
    clock: Callable[[], datetime] = _utc_now

    async def tick(self, *, now: datetime | None = None) -> tuple[DispatchResult, ...]:
        """Claim everything due at ``now``, run it, and report what happened."""
        moment = now or self.clock()
        async with self.gateway.begin_system() as system:
            claims = await JobClaimer(dispatcher=system.jobs, worker_id=self.worker_id).claim_due(
                now=moment
            )
        return tuple([await self.run_claim(claim, now=moment) for claim in claims])

    async def run_claim(self, claim: JobClaim, *, now: datetime | None = None) -> DispatchResult:
        """Run one claimed job and release the claim whichever way it ended."""
        moment = now or self.clock()
        scope = TenantScope(org_id=claim.org_id)

        job = await self._job(claim, scope)
        if job is None:
            result = DispatchResult(
                job_id=claim.job_id,
                kind="",
                outcome=JobOutcome.FAILED,
                failure=(
                    f"The job {claim.job_id!r} was gone by the time its claim was run. "
                    "It was deleted between being claimed and being dispatched."
                ),
            )
            await self._release(claim, result, at=moment)
            return result

        dispatched = await self.dispatcher.dispatch(
            JobContext(claim=claim, job=job, scope=scope, fire_time=moment)
        )
        # Rescheduled on failure as well as on success. A sync that failed
        # tonight still syncs tomorrow: a failure is a bad run, not a deletion,
        # and leaving it unscheduled would turn one unreachable wiki into a job
        # that never runs again and never says it stopped.
        result = DispatchResult(
            job_id=dispatched.job_id,
            kind=dispatched.kind,
            outcome=dispatched.outcome,
            record=dispatched.record,
            failure=dispatched.failure,
            next_run_at=next_due(job, after=moment),
        )
        await self._release(claim, result, at=moment)
        return result

    # -- internals -------------------------------------------------------------

    async def _job(self, claim: JobClaim, scope: TenantScope) -> ScheduledJob | None:
        """Return the job ``claim`` is for, or ``None`` if it has gone."""
        async with self.gateway.begin(scope) as uow:
            return await uow.schedules.get_job(claim.job_id)

    async def _release(self, claim: JobClaim, result: DispatchResult, *, at: datetime) -> None:
        """Release ``claim`` with the outcome, and never raise into the tick.

        A release that failed must not stop the rest of the batch: the other
        claims in this tick are other tenants' jobs, and one store error is not
        a reason for the night's remaining work not to run.
        """
        async with self.gateway.begin_system() as system:
            claimer = JobClaimer(dispatcher=system.jobs, worker_id=self.worker_id)
            try:
                await claimer.release(
                    claim,
                    outcome=result.outcome,
                    completed_at=at,
                    next_run_at=result.next_run_at,
                )
            except PersistenceError as error:
                logger.warning("scheduler.release_failed", job_id=claim.job_id, error=str(error))


__all__ = [
    "DispatchResult",
    "JobContext",
    "JobKindDispatcher",
    "JobRunner",
    "ScheduledJobWorker",
    "UnknownJobKind",
    "next_due",
]
