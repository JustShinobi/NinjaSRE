"""What each of the five verdicts causes, and why only one of them undoes anything.

Verification reaches a verdict; this decides what happens next. The mapping is
short and every line of it was a decision:

``effective``
    The incident closes with the before-and-after values and the time it took.

``ineffective``
    The incident escalates. Nothing is rolled back. An action that did nothing
    is left in place, because undoing it would be a second unattended write with
    no evidence that it helps.

``worsened``
    The rollback plan runs, automatically, and the rollback is itself verified
    through the same mechanism. This is the only verdict that writes anything,
    and it is narrow on purpose: the state the action replaced is known to have
    been better, which is not true of the other four.

``inconclusive``
    The incident escalates, saying what was tried and that the effect could not
    be measured. Nothing is rolled back — there is no evidence the change was
    harmful, and undoing a change on no evidence is the same unattended write.

``unverifiable``
    Recorded and escalated. Whether such an action may run unattended at all was
    already a policy decision made before it ran; this is the record that it did.

**A failed rollback stops everything on that resource.** At that point the
deployment has changed something, failed to undo it, and does not know what
state the resource is in. It escalates at the highest severity with both
failures and suspends autonomous action there until a person clears it.

**A rollback that is no longer possible says so.** The world moved on, the plan
does not match the target, or there was never a derivable plan — three different
facts, one disposition, and all three stated rather than skipped. The incident
still escalates, because the change that made things worse is still in place.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.closed_loop import CLOSED_LOOP_AUDIT_ACTION_ROLLED_BACK
from platform.observability.logging import get_logger
from platform.persistence.ports.remediation_ledger import (
    RecurringProblem,
    RemediationLedger,
    RemediationOutcome,
    RollbackDisposition,
    VerificationVerdict,
)
from platform.remediation.errors import (
    RemediationError,
    RollbackFailed,
    RollbackTargetMismatch,
    RollbackWindowClosed,
)
from platform.remediation.models import RemediationAction, RollbackPlan, utc_now
from platform.remediation.obligations import Verification
from platform.remediation.recurrence import RecurrenceWatch
from platform.remediation.suspension import AutonomySuspensions

_LOG = get_logger(__name__)

#: Where the plan and the action live inside the ledger row's undo payload. Two
#: constants because the row is written by one module and read by another, and a
#: typo between them is an automatic rollback that silently never happens.
UNDO_PLAN = "plan"
UNDO_ACTION = "action"


def undo_payload(action: RemediationAction, plan: RollbackPlan) -> dict[str, Any]:
    """Return what the ledger row carries so a rollback can be run from it alone.

    Both, and in their stored forms. An automatic rollback happens after a
    settle period that may span a restart, and an autonomous action has no
    approval to read the plan back from — so if it is not on the row there is
    nowhere else it could come from.
    """
    return {UNDO_ACTION: action.to_payload(), UNDO_PLAN: plan.to_record()}


def undo_of(outcome: RemediationOutcome) -> tuple[RemediationAction, RollbackPlan] | None:
    """Return the action and plan ``outcome`` carries, or ``None`` if it carries none."""
    stored = dict(outcome.undo)
    action_payload = stored.get(UNDO_ACTION)
    plan_record = stored.get(UNDO_PLAN)
    if not isinstance(action_payload, dict) or not isinstance(plan_record, dict):
        return None
    plan = RollbackPlan.of_record(plan_record)
    if not plan.is_derivable:
        return None
    return RemediationAction.of_payload(action_payload), plan


def _converged(applied: Any) -> bool:
    """Return whether a rollback result says the target came back.

    Structural, because ``PlanApplier`` is a protocol and a deployment may
    supply something other than ``RollbackResult``. An applier that reports no
    opinion is taken at its word — it raised nothing, which is the contract —
    and one that reports ``verified`` is believed either way.
    """
    verified = getattr(applied, "verified", None)
    return verified is not False


@runtime_checkable
class PlanApplier(Protocol):
    """Applies one recorded rollback plan and verifies its own result.

    Narrower than ``RollbackExecutor`` so this module can be driven without a
    step runner, a state reader, and a control plane — and so a deployment that
    reverses changes some other way can supply its own without this package
    knowing.
    """

    async def apply(
        self,
        plan: RollbackPlan,
        *,
        action: RemediationAction,
        now: datetime | None = None,
    ) -> Any:
        """Return what the plan achieved, or raise a ``RemediationError`` saying why not."""


@runtime_checkable
class OutcomeListener(Protocol):
    """Whatever this deployment tells about a verification's consequence.

    A protocol rather than an incident service, for the reason
    ``RemediationAuditor``'s notifier is one: which surface a deployment wants
    told is its own decision, and this package's guarantee is that something is
    told and that it is told with everything needed to act.
    """

    async def resolved(self, aftermath: Aftermath) -> None:
        """The action worked and its incident may close."""

    async def escalated(self, aftermath: Aftermath) -> None:
        """The action did not work, or nobody could tell. A human is needed."""

    async def recurrence(self, problem: RecurringProblem) -> None:
        """A pattern was raised, distinct from any incident."""


@dataclass(frozen=True, slots=True)
class Aftermath:
    """What one verdict caused, in full, for the timeline and the audit chain.

    One value rather than a return code, because six things read it — the
    timeline, the audit trail, the notifier, the console, the CLI and the
    memory — and six signatures spelling the same facts is six places for them
    to drift apart.
    """

    verification: Verification
    outcome: RemediationOutcome
    escalated: bool = False
    severity: str = ""
    rollback: RollbackDisposition = RollbackDisposition.NOT_REQUIRED
    rollback_detail: str = ""
    suspended: bool = False
    problem: RecurringProblem | None = None

    @property
    def verdict(self) -> VerificationVerdict:
        """Return the verdict this followed from."""
        return self.verification.verdict

    @property
    def resolved(self) -> bool:
        """Return whether the incident may close on this."""
        return self.verdict.is_success

    def describe(self) -> str:
        """Return the sentence an operator reads on the timeline."""
        head = self.verification.describe()
        if self.verdict is VerificationVerdict.EFFECTIVE:
            return f"{head} The condition cleared, so the incident is resolved."
        parts = [head]
        if self.rollback is RollbackDisposition.ROLLED_BACK:
            parts.append("The change was rolled back automatically and the rollback verified.")
        elif self.rollback is RollbackDisposition.FAILED:
            parts.append(
                f"The automatic rollback also failed ({self.rollback_detail}), so autonomous "
                f"action on this resource is suspended until a person clears it."
            )
        elif self.rollback is RollbackDisposition.IMPOSSIBLE:
            parts.append(f"The change could not be rolled back: {self.rollback_detail}")
        if self.problem is not None:
            parts.append(
                f"This is occurrence {self.problem.occurrences} inside the window, so it is "
                f"now a recurring problem: {self.problem.title}."
            )
        if self.escalated:
            parts.append("The incident is escalated rather than closed.")
        return " ".join(parts)

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the audit chain and the API response carry."""
        return {
            "action_id": self.outcome.action_id,
            "capability": self.outcome.capability,
            "resource_id": self.outcome.resource_id,
            "verdict": self.verdict.value,
            "before": dict(self.verification.before),
            "after": dict(self.verification.after),
            "settle_seconds": self.outcome.settle_seconds,
            "escalated": self.escalated,
            "severity": self.severity,
            "rollback": self.rollback.value,
            "rollback_detail": self.rollback_detail,
            "suspended": self.suspended,
            "recurring_problem": self.problem.problem_id if self.problem is not None else "",
        }


#: What a failed rollback escalates at. The highest this deployment has, because
#: at that point nobody knows what state the resource is in.
HIGHEST_SEVERITY = "critical"

#: What an ineffective, inconclusive or unverifiable verdict escalates at. Below
#: critical deliberately: nothing is known to have got worse, and an escalation
#: that pages at the same level as an unrecoverable state is one people learn to
#: ignore for both.
ESCALATION_SEVERITY = "high"


@dataclass(slots=True)
class VerificationAftermath:
    """Turns one verdict into the rollback, escalation, suspension and pattern it causes.

    Holds four collaborators and no state. Every one of them is optional except
    the ledger, because a deployment that has not wired an incident service, a
    rollback runner or a recurrence watch should still reach and record a
    verdict — the alternative is a closed loop that refuses to close until every
    surface is configured.
    """

    ledger: RemediationLedger
    suspensions: AutonomySuspensions | None = None
    recurrence: RecurrenceWatch | None = None
    applier: PlanApplier | None = None
    listener: OutcomeListener | None = None
    auditor: Any | None = None
    clock: Callable[[], datetime] = field(default=utc_now)

    async def apply(self, verification: Verification, *, now: datetime | None = None) -> Aftermath:
        """Return what ``verification``'s verdict caused, having caused it."""
        at = now if now is not None else self.clock()
        verdict = verification.verdict

        if verdict is VerificationVerdict.WORSENED:
            aftermath = await self._undo(verification, at=at)
        elif verdict.is_success:
            aftermath = Aftermath(verification=verification, outcome=verification.outcome)
        else:
            aftermath = Aftermath(
                verification=verification,
                outcome=verification.outcome,
                escalated=True,
                severity=ESCALATION_SEVERITY,
            )

        aftermath = await self._observe_recurrence(aftermath, at=at)
        await self._persist(aftermath)
        await self._tell(aftermath)
        return aftermath

    async def _undo(self, verification: Verification, *, at: datetime) -> Aftermath:
        """Roll the change back, verify the rollback, and deal with it failing."""
        outcome = verification.outcome
        undo = undo_of(outcome)

        if self.applier is None or undo is None:
            detail = (
                "no derivable rollback plan was recorded for this action"
                if undo is None
                else "this deployment has no rollback runner wired"
            )
            _LOG.error(
                "remediation.rollback_impossible",
                action_id=outcome.action_id,
                resource_id=outcome.resource_id,
                detail=detail,
            )
            return Aftermath(
                verification=verification,
                outcome=outcome,
                escalated=True,
                severity=HIGHEST_SEVERITY,
                rollback=RollbackDisposition.IMPOSSIBLE,
                rollback_detail=detail,
            )

        action, plan = undo
        try:
            applied = await self.applier.apply(plan, action=action, now=at)
        except (RollbackTargetMismatch, RollbackWindowClosed) as moved_on:
            # The world moved on. Said explicitly rather than skipped, per
            # FR-011: an operator seeing "no rollback" and an operator seeing
            # "the target no longer matches the plan" do different things next.
            return Aftermath(
                verification=verification,
                outcome=outcome,
                escalated=True,
                severity=HIGHEST_SEVERITY,
                rollback=RollbackDisposition.IMPOSSIBLE,
                rollback_detail=str(moved_on),
            )
        except (RollbackFailed, RemediationError) as failed:
            return await self._suspend(verification, detail=str(failed), at=at)

        # FR-009: the rollback is verified through the same mechanism the action
        # was — the target read back through the capability's own reader and
        # compared to the state the plan recorded. An applier that reported
        # success without converging is the failure this feature exists to
        # notice, so the result is checked rather than the absence of an
        # exception.
        if not _converged(applied):
            return await self._suspend(
                verification,
                detail=(
                    "the rollback ran and the target did not come back to the state the "
                    "plan recorded"
                ),
                at=at,
            )

        _LOG.info(
            "remediation.rolled_back_automatically",
            action_id=outcome.action_id,
            resource_id=outcome.resource_id,
            plan_id=plan.plan_id,
        )
        await self._audit_rollback(outcome, detail="rolled back after a worsened verification")
        return Aftermath(
            verification=verification,
            outcome=outcome,
            escalated=True,
            severity=ESCALATION_SEVERITY,
            rollback=RollbackDisposition.ROLLED_BACK,
            rollback_detail="the rollback ran and the target came back to its recorded state",
        )

    async def _suspend(
        self,
        verification: Verification,
        *,
        detail: str,
        at: datetime,
    ) -> Aftermath:
        """Record both failures and stop autonomous action on the resource."""
        outcome = verification.outcome
        _LOG.error(
            "remediation.rollback_failed_autonomy_suspended",
            action_id=outcome.action_id,
            resource_id=outcome.resource_id,
            detail=detail,
        )
        suspended = False
        if self.suspensions is not None:
            await self.suspensions.suspend(
                outcome.resource_id,
                reason=(
                    f"{outcome.capability} made things worse and the rollback failed: "
                    f"{detail} Nobody knows what state this resource is in."
                ),
                action_id=outcome.action_id,
                at=at,
            )
            suspended = True
        await self._audit_rollback(outcome, detail=f"rollback failed: {detail}")
        return Aftermath(
            verification=verification,
            outcome=outcome,
            escalated=True,
            severity=HIGHEST_SEVERITY,
            rollback=RollbackDisposition.FAILED,
            rollback_detail=detail,
            suspended=suspended,
        )

    async def _observe_recurrence(self, aftermath: Aftermath, *, at: datetime) -> Aftermath:
        """Return ``aftermath`` carrying the pattern this occurrence raised, if any."""
        if self.recurrence is None:
            return aftermath
        problem = await self.recurrence.observe(aftermath.outcome, now=at)
        if problem is None:
            return aftermath
        return replace(aftermath, problem=problem)

    async def _persist(self, aftermath: Aftermath) -> None:
        """Write the rollback disposition back onto the ledger row."""
        stored = replace(
            aftermath.outcome,
            rollback=aftermath.rollback,
            rollback_detail=aftermath.rollback_detail,
        )
        await self.ledger.record(stored)

    async def _tell(self, aftermath: Aftermath) -> None:
        """Tell whatever this deployment has wired, and never fail because of it."""
        if self.listener is None:
            return
        if aftermath.problem is not None:
            await self.listener.recurrence(aftermath.problem)
        if aftermath.resolved:
            await self.listener.resolved(aftermath)
        else:
            await self.listener.escalated(aftermath)

    async def _audit_rollback(self, outcome: RemediationOutcome, *, detail: str) -> None:
        """Record that a rollback was triggered by a verification, not by a person."""
        if self.auditor is None:
            return
        await self.auditor.rolled_back(
            outcome, action=CLOSED_LOOP_AUDIT_ACTION_ROLLED_BACK, detail=detail
        )


__all__ = [
    "ESCALATION_SEVERITY",
    "HIGHEST_SEVERITY",
    "UNDO_ACTION",
    "UNDO_PLAN",
    "Aftermath",
    "OutcomeListener",
    "PlanApplier",
    "VerificationAftermath",
    "undo_of",
    "undo_payload",
]
