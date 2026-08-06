"""Clearing up after a replica that stopped existing.

A worker holding a claim can die in a way that leaves no trace: a pod evicted, a
node lost, a process killed. Everything it was doing is still recorded as
in-flight, and the two things left behind need different treatment.

**The lease** is released, and the job's schedule is left exactly where it was —
so the next worker to ask finds it due. That is the entire purpose of a lease
rather than a lock, and it is the store's own behaviour rather than something
this module implements.

**The run** is marked interrupted, and that is what this module adds. The store
releases the lease; nothing releases the run, and a run left as ``running``
forever is worse than one marked interrupted: it sits at the top of a
most-recent-first list looking like something is happening, it counts as active
against any reading of what the deployment is doing, and nobody can tell it from
a genuinely long investigation.

**The two happen in two transactions, in that order, and that is not a
compromise.** Releasing leases is a cross-tenant operation on the system unit of
work; marking a run is a tenant-scoped one — and by design there is no way to
hold both at once, because a caller that could would be a caller that could
deadlock two tenants against each other. The window between them is safe for a
concrete reason rather than a hopeful one: a job re-claimed inside it produces a
run id derived from ``(job_id, fire_time)``, which is the id the abandoned run
already holds, so the store refuses it. The firing cannot run twice however the
two transactions interleave.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from config.constants.runs import RUN_METADATA_JOB
from platform.observability.logging import get_logger
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.run_trace_store import RunStatus, RunTraceStore
from platform.persistence.ports.schedule_store import JobClaim
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.runs.recorder import RunRecorder

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ReapReport:
    """What one reaping pass released and marked."""

    leases_expired: int = 0
    runs_interrupted: int = 0
    jobs: tuple[str, ...] = ()

    @property
    def happened(self) -> bool:
        """Return whether the pass found anything to clear up."""
        return bool(self.leases_expired)


@dataclass(slots=True)
class LeaseReaper:
    """Releases expired leases and marks the runs they abandoned.

    Holds a gateway rather than a dispatcher, because the pass genuinely spans
    the tenant boundary: the leases come off the system unit of work and each
    abandoned run is written inside its own tenant's.

    ``recorder_for`` builds the recorder a tenant's run is marked through, so a
    deployment that wires guardrails or a broker into its recorders gets the
    same one here — an interruption is a trace event like any other, and one
    written by a recorder configured differently would be the one event the
    console did not receive.
    """

    gateway: PersistenceGateway
    recorder_for: Callable[[RunTraceStore], RunRecorder] = RunRecorder
    clock: Callable[[], datetime] = _utc_now

    async def reap(self, *, now: datetime | None = None) -> ReapReport:
        """Release every expired lease and mark its run, and report what went."""
        moment = now or self.clock()

        async with self.gateway.begin_system() as system:
            expired = await system.jobs.expire_leases(now=moment)

        if not expired:
            return ReapReport()

        interrupted = 0
        for org_id, claims in _by_tenant(expired).items():
            interrupted += await self._interrupt(org_id, claims)

        report = ReapReport(
            leases_expired=len(expired),
            runs_interrupted=interrupted,
            jobs=tuple(claim.job_id for claim in expired),
        )
        logger.warning(
            "scheduler.leases_reaped",
            leases=report.leases_expired,
            runs=report.runs_interrupted,
            jobs=list(report.jobs),
        )
        return report

    async def _interrupt(self, org_id: str, claims: Sequence[JobClaim]) -> int:
        """Mark one tenant's abandoned runs, and return how many were marked.

        Found by *job*, not by run id. A claim carries the job's payload as it
        stood when the claim was taken, so it cannot say which firing the dead
        worker reached — but a job has at most one unfinished run at a time,
        because that is what the claim itself guaranteed while it was held.

        A job with no unfinished run contributes nothing and is not an error: a
        worker can die between claiming a job and starting its run, and then the
        lease released is the whole of the tidying.
        """
        by_job = {claim.job_id: claim for claim in claims}
        marked = 0

        async with self.gateway.begin(TenantScope(org_id=org_id)) as uow:
            recorder = self.recorder_for(uow.run_traces)
            for run in await uow.run_traces.list_runs(status=RunStatus.RUNNING):
                claim = by_job.get(str(run.metadata.get(RUN_METADATA_JOB, "")))
                if claim is None:
                    continue
                try:
                    await recorder.mark_interrupted(
                        run.run_id, reason=f"the lease held by {claim.worker_id} expired"
                    )
                except RecordNotFound:  # pragma: no cover — listed moments earlier
                    continue
                marked += 1
        return marked


def _by_tenant(claims: Sequence[JobClaim]) -> dict[str, list[JobClaim]]:
    """Return ``claims`` grouped by the organisation they belong to."""
    grouped: dict[str, list[JobClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.org_id, []).append(claim)
    return grouped


__all__ = ["LeaseReaper", "ReapReport"]
