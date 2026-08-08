"""The loop, composed: claim what is due, read it back, and deal with the answer.

Everything else in this package is a piece. This is the object a deployment
wires and the worker calls, and it is deliberately thin — five collaborators and
one method that runs them in an order that is the specification:

1. **Claim** the obligations that are due, with a lease, so two replicas divide
   them rather than both verifying one action.
2. **Settle** each one: read the declared signals, compare, record the verdict.
3. **Deal with it**: roll back a worsened change, escalate anything that is not
   success, suspend a resource whose rollback failed, raise a pattern on the
   fourth occurrence.
4. **Tell the incident**, on its own timeline, with the actor and the cause.
5. **Feed memory**, so the next proposal knows.

**A verdict is recorded before anything acts on it.** Step 2 writes; step 3
reads what was written. A worker that died between them leaves a verdict and no
rollback, which is recoverable and visible; the other order leaves a rollback
nobody can explain.

**One obligation's failure does not stop the sweep.** A capability whose reader
raises would otherwise hold up every other verification the deployment owes, and
the ones behind it are the ones nobody has looked at yet.

**The sweep is a scheduled job.** Claiming it is the scheduler's existing lease,
exactly as the observation tick is, which is what hands the work across the
tenant boundary without this package inventing a second way to do it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config.constants.closed_loop import (
    CLOSED_LOOP_AUDIT_ACTION_RECURRENCE,
    CLOSED_LOOP_AUDIT_ACTION_VERIFIED,
    CLOSED_LOOP_AUDIT_RESOURCE_KIND,
    MAX_VERIFICATION_CLAIM_BATCH,
    VERIFICATION_LEASE_SECONDS,
    VERIFICATION_SWEEP_INTERVAL_SECONDS,
    VERIFICATION_SWEEP_JOB_KIND,
    VERIFICATION_SWEEP_LEASE_SECONDS,
)
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, AuditEvent, AuditOutcome, AuditRepository
from platform.persistence.ports.remediation_ledger import RecurringProblem
from platform.persistence.ports.schedule_store import JobClaim, JobDispatcher, ScheduledJob
from platform.remediation.aftermath import Aftermath, VerificationAftermath
from platform.remediation.history import EffectivenessMemory
from platform.remediation.models import utc_now
from platform.remediation.obligations import Verification, VerificationObligations
from platform.remediation.suspension import SUSPENSION_ACTOR
from platform.scheduler.claiming import JobClaimer

_LOG = get_logger(__name__)

#: The scheduled job every deployment has exactly one of. Derived rather than
#: generated, so re-registering the sweep updates its schedule instead of adding
#: a second one that verifies everything twice as often.
SWEEP_JOB_ID = f"{VERIFICATION_SWEEP_JOB_KIND}:estate"


def verification_sweep_job(
    *,
    next_run_at: datetime,
    interval_seconds: int = VERIFICATION_SWEEP_INTERVAL_SECONDS,
) -> ScheduledJob:
    """Return the recurring job that settles due verification obligations."""
    return ScheduledJob(
        job_id=SWEEP_JOB_ID,
        name="Settle the verifications that have come due",
        kind=VERIFICATION_SWEEP_JOB_KIND,
        schedule=f"every {interval_seconds}s",
        next_run_at=next_run_at,
        payload={"interval_seconds": interval_seconds},
    )


def next_sweep_after(claim: JobClaim, *, now: datetime) -> datetime:
    """Return when the deployment is due to sweep its obligations again."""
    raw = claim.payload.get("interval_seconds", VERIFICATION_SWEEP_INTERVAL_SECONDS)
    try:
        interval = int(str(raw))
    except (TypeError, ValueError):
        interval = VERIFICATION_SWEEP_INTERVAL_SECONDS
    return now + timedelta(seconds=max(interval, 1))


@dataclass(frozen=True, slots=True)
class SweepClaiming:
    """A worker's view of claiming sweeps, over the scheduler's own claimer.

    A thin wrapper rather than a second mechanism, exactly as observation's is.
    Everything it adds is the sweep's lease length and the filter that keeps a
    verification worker from claiming somebody else's job.
    """

    claimer: JobClaimer

    @classmethod
    def for_worker(cls, dispatcher: JobDispatcher, worker_id: str) -> SweepClaiming:
        """Return claiming for ``worker_id``, with the sweep's lease length."""
        return cls(
            claimer=JobClaimer(
                dispatcher=dispatcher,
                worker_id=worker_id,
                lease_seconds=VERIFICATION_SWEEP_LEASE_SECONDS,
            )
        )

    async def claim(self, *, now: datetime) -> tuple[JobClaim, ...]:
        """Return the sweeps due at ``now`` that no other worker has."""
        claims = await self.claimer.claim_due(now=now)
        return tuple(claim for claim in claims if claim.job_id == SWEEP_JOB_ID)


@dataclass(frozen=True, slots=True)
class SweepOutcome:
    """What one sweep settled, and what it could not.

    ``deferred`` is separate from ``settled`` because a metrics pipeline one poll
    behind produces deferrals rather than verdicts, and a sweep reporting them as
    settled would make a quiet estate indistinguishable from a broken one.
    """

    claimed: int = 0
    settled: tuple[Aftermath, ...] = ()
    deferred: int = 0
    failed: tuple[str, ...] = ()

    def describe(self) -> str:
        """Return the line a worker logs about one pass."""
        return (
            f"claimed {self.claimed}, settled {len(self.settled)}, deferred {self.deferred}, "
            f"failed {len(self.failed)}"
        )


@dataclass(slots=True)
class ClosedLoopAuditor:
    """The audit row for a verdict, and for the pattern one may raise.

    Written whichever way the verdict went, and with the same shape for all
    five. An operator asking "what did the deployment conclude about what it
    did last night" writes one query, and a second shape for the failures would
    mean the half that explains why an incident is still open is the half that
    does not appear.
    """

    audit: AuditRepository
    actor_id: str = SUSPENSION_ACTOR

    async def verified(self, aftermath: Aftermath) -> None:
        """Record one verdict and everything it caused."""
        outcome = aftermath.outcome
        await self._append(
            action=CLOSED_LOOP_AUDIT_ACTION_VERIFIED,
            resource_id=outcome.action_id,
            at=outcome.verified_at or utc_now(),
            outcome=(AuditOutcome.ALLOWED if aftermath.resolved else AuditOutcome.FAILED),
            detail=aftermath.to_record(),
        )

    async def recurrence(self, problem: RecurringProblem) -> None:
        """Record that a pattern was raised, distinct from any incident."""
        await self._append(
            action=CLOSED_LOOP_AUDIT_ACTION_RECURRENCE,
            resource_id=problem.problem_id,
            at=problem.raised_at,
            outcome=AuditOutcome.DENIED,
            detail={
                "pattern_key": problem.pattern_key,
                "capability": problem.capability,
                "resource_id": problem.resource_id,
                "occurrences": problem.occurrences,
                "window_seconds": problem.window_seconds,
                "action_ids": list(problem.action_ids),
                "suppresses_autonomy": problem.suppresses_autonomy,
            },
        )

    async def rolled_back(self, outcome: object, *, action: str, detail: str) -> None:
        """Record that a rollback was triggered by a verification, not by a person."""
        action_id = str(getattr(outcome, "action_id", ""))
        await self._append(
            action=action,
            resource_id=action_id,
            at=utc_now(),
            outcome=AuditOutcome.DENIED,
            detail={
                "action_id": action_id,
                "resource_id": str(getattr(outcome, "resource_id", "")),
                "detail": detail,
            },
        )

    async def _append(
        self,
        *,
        action: str,
        resource_id: str,
        at: datetime,
        outcome: AuditOutcome,
        detail: dict[str, object],
    ) -> None:
        """Append one immutable row, tolerating the retry that writes it twice."""
        from platform.persistence.errors import DuplicateRecord

        try:
            await self.audit.append(
                AuditEvent(
                    event_id=f"{action}:{resource_id}:{at.isoformat()}",
                    occurred_at=at,
                    actor_kind=ActorKind.SYSTEM,
                    actor_id=self.actor_id,
                    action=action,
                    resource_kind=CLOSED_LOOP_AUDIT_RESOURCE_KIND,
                    resource_id=resource_id,
                    outcome=outcome,
                    detail=detail,
                )
            )
        except DuplicateRecord:
            _LOG.debug("remediation.audit_row_already_recorded", action=action, id=resource_id)


@dataclass(slots=True)
class ClosedLoop:
    """Claim what is due, settle it, and deal with what it says.

    The five collaborators are separate because they fail separately and are
    wired separately: a deployment with no incident service still verifies, and
    one with memory writing ablated still rolls back. What is not optional is
    the pair at the top — without them there is no loop.
    """

    obligations: VerificationObligations
    aftermath: VerificationAftermath
    memory: EffectivenessMemory | None = None
    auditor: ClosedLoopAuditor | None = None
    clock: Callable[[], datetime] = field(default=utc_now)

    async def sweep(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        lease_seconds: float = VERIFICATION_LEASE_SECONDS,
        limit: int = MAX_VERIFICATION_CLAIM_BATCH,
    ) -> SweepOutcome:
        """Settle every obligation due at ``now`` that no other worker holds."""
        at = now if now is not None else self.clock()
        claimed = await self.obligations.claim(
            worker_id=worker_id, now=at, lease_seconds=lease_seconds, limit=limit
        )

        settled: list[Aftermath] = []
        failed: list[str] = []
        deferred = 0

        for row in claimed:
            try:
                verification = await self.obligations.settle(row, now=at)
            except Exception as refused:  # noqa: BLE001 — one obligation's problem
                # Recorded and stepped over. A capability whose reader raises
                # would otherwise hold up every other verification the
                # deployment owes, and those are the ones nobody has read yet.
                _LOG.error(
                    "remediation.verification_failed",
                    action_id=row.action_id,
                    capability=row.capability,
                    error=f"{type(refused).__name__}: {refused}",
                )
                failed.append(row.action_id)
                continue

            if not verification.settled:
                deferred += 1
                continue

            settled.append(await self.conclude(verification, now=at))

        outcome = SweepOutcome(
            claimed=len(claimed),
            settled=tuple(settled),
            deferred=deferred,
            failed=tuple(failed),
        )
        _LOG.info("remediation.sweep", worker_id=worker_id, summary=outcome.describe())
        return outcome

    async def conclude(
        self,
        verification: Verification,
        *,
        now: datetime | None = None,
    ) -> Aftermath:
        """Deal with one verdict: act on it, audit it, and feed memory."""
        at = now if now is not None else self.clock()
        aftermath = await self.aftermath.apply(verification, now=at)

        if self.auditor is not None:
            await self.auditor.verified(aftermath)
            if aftermath.problem is not None:
                await self.auditor.recurrence(aftermath.problem)
        if self.memory is not None:
            await self.memory.record(verification)
        return aftermath


__all__ = [
    "SWEEP_JOB_ID",
    "ClosedLoop",
    "ClosedLoopAuditor",
    "SweepClaiming",
    "SweepOutcome",
    "next_sweep_after",
    "verification_sweep_job",
]
