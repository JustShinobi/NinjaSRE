"""The scheduled pass that comes back for the verdicts this deployment owes.

``ClosedLoop`` claims due obligations, reads the declared signals back, records
the verdict, rolls a worsened change back, escalates anything that is not
success, and writes what happened onto the incident and onto the run's episode.
All of it was written, tested and merged, and no deployment ever ran a line of
it: the scheduler dispatched two kinds of job and neither was the sweep. One
staging remediation therefore sat in ``awaiting_verification`` for a day, its due
time forty seconds after the change, in front of a screen whose word for that
state means "ask again shortly".

This is the root that serves it, and it is deliberately thin — everything here
is a wiring decision the pieces below cannot make for themselves.

**The loop is built per tick, inside one unit of work.** Its collaborators are
five ports on one transaction, and a loop constructed at boot would hold a
transaction for the life of the process. Per tick is also what makes the sweep
scoped to the tenant whose job was claimed.

**The incident comes from the run, not from the row.** The obligation carries the
run that acted, because that is what the executor has; the incident is what the
run was started for. Joining them here rather than in ``platform/`` is the same
call ``ObservationTickJobRunner`` makes about the estate and the exporter — two
facts that live apart, joined at the layer allowed to hold both. Without the
join the verdict lands in a ledger and the incident it answers stays open.

**A deployment with no desk sweeps nothing and says so.** It has no executor, so
it owes no verdicts; a runner that raised would turn "this deployment does not
write to production" into a job that fails every thirty seconds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from config.constants.closed_loop import MAX_EFFECTIVENESS_PAGE_SIZE
from gateway.http.state import GatewayState
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observability.logging import get_logger
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    RemediationOutcome,
    VerificationState,
)
from platform.persistence.ports.transaction import TenantScope, UnitOfWork
from platform.remediation.aftermath import VerificationAftermath
from platform.remediation.closed_loop import (
    ClosedLoop,
    ClosedLoopAuditor,
    verification_sweep_job,
)
from platform.remediation.history import EffectivenessMemory
from platform.remediation.obligations import VerificationObligations
from platform.remediation.recurrence import RecurrenceWatch
from platform.remediation.suspension import AutonomySuspensions
from platform.remediation.timeline import IncidentOutcomes
from platform.scheduler.dispatch import JobContext

logger = get_logger(__name__)

#: What the sweep calls itself when it takes a lease on an obligation. Distinct
#: from the scheduler's own worker id, because the two claim different things
#: and an operator reading a stuck lease needs to know which pass is holding it.
SWEEP_WORKER_ID = "gateway:verification"


@dataclass(frozen=True, slots=True)
class VerificationSweepJobRunner:
    """Settles every verification obligation that has come due for one tenant."""

    state: GatewayState

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Claim what is due at the fire time, settle it, and report what went."""
        desk = getattr(self.state, "remediation", None)
        if desk is None:
            logger.info(
                "remediation.sweep_skipped",
                reason="this deployment composed no remediation desk, so it owes no verdicts",
            )
            return {"claimed": 0, "settled": 0, "deferred": 0, "failed": 0}

        async with self.state.gateway.begin(context.scope) as uow:
            await self._bind_incidents(uow, now=context.fire_time)
            outcome = await self._loop(uow, desk).sweep(
                worker_id=SWEEP_WORKER_ID, now=context.fire_time
            )

        return {
            "claimed": outcome.claimed,
            "settled": len(outcome.settled),
            "deferred": outcome.deferred,
            "failed": len(outcome.failed),
        }

    def _loop(self, uow: UnitOfWork, desk: Any) -> ClosedLoop:
        """Return the closed loop over one transaction's ports."""
        incidents = IncidentLifecycle(store=uow.incidents)
        return ClosedLoop(
            obligations=VerificationObligations(
                ledger=uow.remediation,
                signals=uow.signals,
                registry=desk.components,
            ),
            aftermath=VerificationAftermath(
                ledger=uow.remediation,
                suspensions=AutonomySuspensions(audit=uow.audit),
                recurrence=RecurrenceWatch(ledger=uow.remediation),
                listener=IncidentOutcomes(incidents=incidents),
            ),
            memory=EffectivenessMemory(episodes=uow.episodes),
            auditor=ClosedLoopAuditor(audit=uow.audit),
        )

    async def _bind_incidents(self, uow: UnitOfWork, *, now: datetime) -> None:
        """Stamp each owed obligation with the incident its run was started for.

        The executor writes the row knowing the action and the run and nothing
        else — an incident is not a field on a remediation action, and inventing
        one there would make every caller that builds an action responsible for
        finding it. So the join happens once, here, against the binding the run
        already has: without it ``IncidentOutcomes`` reads an empty incident id
        and returns, and a verified remediation leaves its incident open.

        Only rows that are still owed and still unbound are touched, so this
        costs one query per sweep on a deployment that has caught up.
        """
        bound = 0
        for row in await _open_obligations(uow, now=now):
            incident = await uow.incidents.find_by_run(row.run_id)
            if incident is None:
                continue
            await uow.remediation.record(replace(row, incident_id=incident.incident_id))
            bound += 1
        if bound:
            logger.info("remediation.obligations_bound_to_incidents", bound=bound)


async def _open_obligations(uow: UnitOfWork, *, now: datetime) -> tuple[RemediationOutcome, ...]:
    """Return the obligations due at ``now`` that carry no incident yet.

    Bounded at the ledger's own page ceiling rather than at the claim batch. The
    two are ordered differently — this reads most-recently-executed first and a
    claim takes the longest-overdue — so matching the batch size would bind the
    newest twenty-five while settling the oldest twenty-five, which is a join
    that silently covers the wrong rows. A backlog deeper than one page binds
    over successive sweeps, thirty seconds apart.
    """
    rows = await uow.remediation.history(
        EffectivenessQuery(
            states=(VerificationState.AWAITING,),
            until=now,
            limit=MAX_EFFECTIVENESS_PAGE_SIZE,
        )
    )
    return tuple(row for row in rows if row.run_id and not row.incident_id)


async def schedule_verification_sweep(state: GatewayState, *, org_id: str) -> bool:
    """Register the recurring pass that settles what this deployment's writes owe.

    Upserted rather than created, for the reason the observation tick's
    registration gives: a restart must not accumulate a job per boot, and an
    operator who changed the interval keeps their change.

    Returns whether the row was written, and never raises. This runs while the
    desk is being composed, and a store that is a moment from being reachable
    must not take the desk down with it — a deployment that cannot register the
    sweep can still propose, approve and execute, and it is the next boot or an
    operator that fixes the registration. The failure is a warning naming what
    it costs rather than a line saying a write failed, because what it costs is
    that nothing will come back for the verdicts.
    """
    job = verification_sweep_job(next_run_at=datetime.now(UTC))
    try:
        async with state.gateway.begin(TenantScope(org_id=org_id)) as uow:
            await uow.schedules.upsert_job(job)
    except Exception as unreachable:  # noqa: BLE001 — recorded, and never fatal at boot
        logger.warning(
            "remediation.sweep_not_scheduled",
            job_id=job.job_id,
            error=str(unreachable),
            consequence=(
                "nothing will settle this deployment's verification obligations, so every "
                "remediation it carries out will report awaiting verification for ever"
            ),
        )
        return False
    logger.info("remediation.sweep_scheduled", job_id=job.job_id)
    return True


__all__ = [
    "SWEEP_WORKER_ID",
    "VerificationSweepJobRunner",
    "schedule_verification_sweep",
]
