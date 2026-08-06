"""Checking that a plan is still about the system it was written for.

A rollback plan is a description of how to get *back to a state*. Applying it to
a different state is not a rollback — it is a second unreviewed change, made
under the authority of the first, and it is the way a recovery turns into an
incident of its own. So the plan carries two snapshots, and this module compares
the right one against what is there now.

**The right one is the post-execution snapshot, not the pre-execution one.** A
plan's ``recorded_state`` is where the undo goes; its ``applied_state`` is what
the undo expects to find. Checking against the first would refuse every
legitimate rollback, because the action's whole effect is that the target no
longer looks like that — a mistake worth naming here because the code reads
plausibly either way.

Two checks, both refusals rather than warnings.

**The target still looks the way the plan left it.** Fingerprint against
fingerprint, so a workload somebody has since taken from twelve replicas to two
does not receive a plan written to put it back to four.

**The window has not closed.** One-click rollback exists for the hour after a
change, while the person who approved it still holds the context. Later, undoing
it is a fresh change against fresh state, and it goes through the approval
mechanism like any other — which is a different, better path than a stale handle
that still works.

An unreadable target refuses too. "We could not read it" is not evidence that it
matches, and treating it as a match is exactly how a plan lands blind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from config.constants.security import REMEDIATION_ROLLBACK_WINDOW_SECONDS
from platform.observability.logging import get_logger
from platform.remediation.errors import RollbackTargetMismatch, RollbackWindowClosed
from platform.remediation.models import RollbackPlan, StateSnapshot

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MatchReport:
    """Whether a plan still applies, and why not when it does not.

    Returned by ``check`` for callers that are deciding what to *show* — a
    console listing which of a run's actions are still rollbackable, say — and
    turned into a refusal by ``require`` for the caller that is about to act.
    Two shapes, because a listing that raised would be a listing that stopped at
    the first stale plan.
    """

    plan_id: str
    target: str
    matches: bool
    expected: str
    observed: str
    reason: str = ""

    def describe(self) -> str:
        """Return the sentence a surface shows beside the rollback button."""
        if self.matches:
            return f"{self.target} still matches the state this plan was recorded against."
        return f"{self.target} cannot be rolled back with this plan: {self.reason}"


def check(plan: RollbackPlan, observed: StateSnapshot) -> MatchReport:
    """Return whether ``plan`` still describes ``observed``.

    Never raises. The comparison is a fact about two snapshots, and a caller
    rendering a queue of past actions needs it for all of them rather than for
    the ones before the first mismatch.
    """
    expected = plan.expected_state
    if not observed.known:
        return MatchReport(
            plan_id=plan.plan_id,
            target=plan.target,
            matches=False,
            expected=expected.fingerprint,
            observed=observed.fingerprint,
            reason=(
                "its current state could not be read, and an unread target is not a matching one"
            ),
        )
    if not expected.matches(observed):
        return MatchReport(
            plan_id=plan.plan_id,
            target=plan.target,
            matches=False,
            expected=expected.fingerprint,
            observed=observed.fingerprint,
            reason=(
                "it has changed since the action ran, so the plan describes a state it is "
                "no longer in"
            ),
        )
    return MatchReport(
        plan_id=plan.plan_id,
        target=plan.target,
        matches=True,
        expected=expected.fingerprint,
        observed=observed.fingerprint,
    )


def require_match(plan: RollbackPlan, observed: StateSnapshot) -> None:
    """Raise ``RollbackTargetMismatch`` unless ``plan`` still describes ``observed``."""
    report = check(plan, observed)
    if report.matches:
        return
    _LOG.error(
        "remediation.rollback_target_mismatch",
        plan_id=plan.plan_id,
        target=plan.target,
        reason=report.reason,
    )
    raise RollbackTargetMismatch(
        plan.plan_id,
        plan.target,
        expected=report.expected,
        observed=report.observed,
    )


def require_window(
    plan: RollbackPlan,
    *,
    now: datetime,
    window_seconds: float = REMEDIATION_ROLLBACK_WINDOW_SECONDS,
) -> None:
    """Raise ``RollbackWindowClosed`` when the one-click window has passed."""
    if plan.within_window(now, window_seconds=window_seconds):
        return
    raise RollbackWindowClosed(plan.plan_id, window_seconds=window_seconds)


__all__ = [
    "MatchReport",
    "check",
    "require_match",
    "require_window",
]
