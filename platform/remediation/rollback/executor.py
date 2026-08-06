"""Applying a recorded plan, checking its own result, and failing loudly.

Everything here is downstream of a decision that was already made: the plan
exists, it was persisted before the action ran, and somebody has asked for it to
be applied. What is left is to do it in the right order and to be honest about
what happened.

**The target is checked before the first step, not after the last.** A plan that
no longer describes the system is refused whole rather than half-applied and
then discovered to be wrong, because a half-applied rollback is a state nobody
designed and nobody has a plan for.

**Which steps completed is recorded, always.** Partial rollbacks are the normal
case when something has gone wrong twice, and knowing that steps one and two ran
and three did not is the difference between a safe retry and a second incident.

**A failure raises and nothing retries it.** There is no automatic second
attempt here and there should not be: the second attempt would run against a
system that is now in a state the plan was not written for, which is the
situation the check at the top exists to prevent. A failed rollback needs human
judgement, and this module's job is to make sure a human hears about it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.security import REMEDIATION_ROLLBACK_WINDOW_SECONDS
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.remediation.components import StateReader
from platform.remediation.errors import RollbackFailed
from platform.remediation.models import (
    RemediationAction,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
    SubTargetResult,
    utc_now,
)
from platform.remediation.rollback import verification

_LOG = get_logger(__name__)


@runtime_checkable
class StepRunner(Protocol):
    """Performs one step of a rollback plan.

    Separate from the capability's applier because a rollback step names the
    capability it calls, and that capability is frequently not the one being
    undone — a scale is reversed by a scale, but a cordon is reversed by an
    uncordon. Resolving the call is the runner's job, and a deployment binds one
    that goes through the same sandbox and the same proxy as anything else.
    """

    async def run(self, step: RollbackStep, *, action: RemediationAction) -> SubTargetResult:
        """Return what this step did, or a result saying it did nothing."""


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """What applying a plan achieved, step by step.

    ``verified`` is separate from "every step ran". A step that reported success
    and left the target somewhere else is the failure this whole feature is
    about, and a result that conflated the two would report it as a clean undo.
    """

    plan_id: str
    target: str
    completed: tuple[int, ...] = ()
    results: tuple[SubTargetResult, ...] = ()
    verified: bool = False
    observed: StateSnapshot | None = None
    executed_at: datetime | None = None

    @property
    def fully_applied(self) -> bool:
        """Return whether every step ran and the target came back as recorded."""
        return self.verified and bool(self.completed)

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which the audit trail carries."""
        return {
            "plan_id": self.plan_id,
            "target": self.target,
            "completed": list(self.completed),
            "results": [result.to_record() for result in self.results],
            "verified": self.verified,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


@dataclass(slots=True)
class RollbackExecutor:
    """Applies one recorded plan, in order, and verifies its own result.

    ``reader`` is the same state reader the action used. One reader for the
    before, the after, and the rollback check, because three would eventually
    disagree about what "the state" is and the comparison would be between two
    different things.
    """

    runner: StepRunner
    reader: StateReader
    gateway: PersistenceGateway | None = None
    scope: TenantScope | None = None
    window_seconds: float = REMEDIATION_ROLLBACK_WINDOW_SECONDS
    clock: Callable[[], datetime] = field(default=utc_now)

    async def apply(
        self,
        plan: RollbackPlan,
        *,
        action: RemediationAction,
        now: datetime | None = None,
    ) -> RollbackResult:
        """Apply ``plan`` and return what it achieved, or raise saying what did not.

        The order is the specification: window, target match, steps, verify,
        record. Moving the record earlier would mean a crash mid-rollback left
        no trace of which steps had run, and moving the checks later would mean
        discovering the plan was inapplicable after applying half of it.
        """
        at = now if now is not None else self.clock()
        verification.require_window(plan, now=at, window_seconds=self.window_seconds)

        observed = await self.reader.read(action, at=at)
        verification.require_match(plan, observed)

        completed, results = await self._run_steps(plan, action)
        after = await self.reader.read(action, at=self.clock())
        verified = plan.recorded_state.matches(after)

        result = RollbackResult(
            plan_id=plan.plan_id,
            target=plan.target,
            completed=tuple(completed),
            results=tuple(results),
            verified=verified,
            observed=after,
            executed_at=at,
        )
        await self._record(result)

        if not verified:
            _LOG.error(
                "remediation.rollback_unverified",
                plan_id=plan.plan_id,
                target=plan.target,
                completed=list(completed),
            )
            raise RollbackFailed(
                plan.plan_id,
                completed=completed,
                detail=(
                    "every step ran but the target did not come back to the state the plan "
                    "recorded."
                    if len(completed) == len(plan.steps)
                    else "it stopped part-way and the target is between two states."
                ),
            )

        _LOG.info(
            "remediation.rollback_applied",
            plan_id=plan.plan_id,
            target=plan.target,
            steps=len(completed),
        )
        return result

    async def _run_steps(
        self, plan: RollbackPlan, action: RemediationAction
    ) -> tuple[list[int], list[SubTargetResult]]:
        """Run the plan's steps in order, stopping at the first that raises.

        Stopping is right. The steps of an undo are ordered because each assumes
        the previous one happened, and continuing past a failure would run step
        three against the state step two was supposed to produce.
        """
        completed: list[int] = []
        results: list[SubTargetResult] = []

        for step in sorted(plan.steps, key=lambda held: held.ordinal):
            try:
                result = await self.runner.run(step, action=action)
            except Exception as failure:  # noqa: BLE001 — reported, never swallowed
                _LOG.error(
                    "remediation.rollback_step_failed",
                    plan_id=plan.plan_id,
                    ordinal=step.ordinal,
                    capability=step.capability,
                    error=str(failure),
                )
                await self._record(
                    RollbackResult(
                        plan_id=plan.plan_id,
                        target=plan.target,
                        completed=tuple(completed),
                        results=tuple(results),
                        executed_at=self.clock(),
                    )
                )
                raise RollbackFailed(
                    plan.plan_id,
                    completed=completed,
                    detail=f"step {step.ordinal} ({step.capability}) failed: {failure}",
                ) from failure

            results.append(result)
            completed.append(step.ordinal)

        return completed, results

    async def _record(self, result: RollbackResult) -> None:
        """Store which steps ran, when a store is wired up.

        Optional, because the executor is usable in a deployment that has not
        wired persistence yet and because a test driving the step order should
        not need a database. When there *is* a store, this is not optional in
        practice: it is the only record of a partial rollback.
        """
        if self.gateway is None or self.scope is None:
            return
        async with self.gateway.begin(self.scope) as uow:
            await uow.approvals.record_rollback_executed(
                result.plan_id,
                executed_at=result.executed_at if result.executed_at else self.clock(),
                completed_steps=result.completed,
            )


__all__ = [
    "RollbackExecutor",
    "RollbackResult",
    "StepRunner",
]
