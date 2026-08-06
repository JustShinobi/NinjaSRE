"""What this package raises, named so the caller can tell the refusals apart.

Every type here is a different reason a production change did not happen, and
each one has a different next step. A kill switch means stop asking; a lapsed
allow-list condition means ask a human; a mismatched rollback target means look
at the system before doing anything else. Collapsing them into one
``RemediationRefused`` would leave the operator with a wall instead of an
instruction, and would leave the agent unable to tell "wait for a person" from
"this will never be permitted".

**A refusal names the action and never the credentials it would have used.**
Execution runs through the credential proxy, so there is nothing here that could
carry one — but the messages are also read out into chat surfaces, and an
exception is one of the places "read out" includes.
"""

from __future__ import annotations

from collections.abc import Sequence


class RemediationError(Exception):
    """Base for every failure raised by the remediation layer."""


# --- Refusals before anything ran --------------------------------------------


class KillSwitchEngaged(RemediationError):
    """A write was requested while the kill switch was on.

    Overrides everything, including an approval that has already been granted.
    That is the whole point of it: during a bad incident an operator must be
    able to stop every automated write with one action, without unwinding
    allow-lists or cancelling approvals one at a time.
    """

    def __init__(self, scope: str, *, engaged_by: str = "", reason: str = "") -> None:
        who = f" by {engaged_by!r}" if engaged_by else ""
        why = f" ({reason})" if reason else ""
        super().__init__(
            f"Every write is refused: the kill switch is engaged for {scope!r}{who}{why}. "
            f"Release it before any remediation can run, including approved ones."
        )
        self.scope = scope
        self.engaged_by = engaged_by
        self.reason = reason


class ConditionsNotMet(RemediationError):
    """An allow-listed action's conditions do not hold.

    Carries every unmet condition rather than the first. Conditions are
    conjunctive, so an operator widening an entry needs to see all of them —
    fixing one and re-running to discover the next is how an allow-list gets
    widened further than anybody intended.
    """

    def __init__(self, capability: str, unmet: Sequence[str]) -> None:
        listed = "\n  - ".join(unmet)
        super().__init__(
            f"{capability!r} is on the autonomous allow-list, but its conditions do not "
            f"hold:\n  - {listed}\nIt needs a human approval instead."
        )
        self.capability = capability
        self.unmet = tuple(unmet)


class ApprovalRefused(RemediationError):
    """A human said no, or nobody said anything before the window closed.

    Both are one type because both leave the system exactly as it was and both
    send the agent back to reasoning without the action. ``expired`` is carried
    so a surface can say which happened, since "declined" and "nobody answered"
    read very differently to the person who asked.
    """

    def __init__(
        self,
        capability: str,
        *,
        approval_id: str = "",
        expired: bool = False,
        reason: str = "",
    ) -> None:
        what = "expired without a decision" if expired else "was declined"
        why = f": {reason}" if reason else "."
        super().__init__(f"The approval for {capability!r} {what}{why}")
        self.capability = capability
        self.approval_id = approval_id
        self.expired = expired
        self.reason = reason


class NoRollbackPlan(RemediationError):
    """An action has no derivable rollback plan and nobody waived the requirement.

    Refused rather than executed with a note. The absence of a plan is itself
    the signal: an action whose undo nobody can write down is riskier than it
    looked when it was proposed, and the moment to notice that is before it
    runs.
    """

    def __init__(self, capability: str, target: str) -> None:
        super().__init__(
            f"{capability!r} against {target!r} has no derivable rollback plan, so it is "
            f"refused. An operator may waive the requirement explicitly, and the waiver "
            f"is audited."
        )
        self.capability = capability
        self.target = target


class TargetLocked(RemediationError):
    """Another action holds this target and did not release it in time.

    Waiting is correct — two concurrent writes to one workload is the case
    serialisation exists for — and waiting forever is not, because an execution
    that hung holding the lock would block every later one with no symptom
    anybody could act on.
    """

    def __init__(self, target: str, *, holder: str = "", waited_seconds: float = 0.0) -> None:
        who = f" held by {holder!r}" if holder else ""
        super().__init__(
            f"{target!r} is already being changed{who}, and it was still held after "
            f"{waited_seconds:g}s. Concurrent actions on one target are serialised."
        )
        self.target = target
        self.holder = holder
        self.waited_seconds = waited_seconds


# --- Refusals during rollback ------------------------------------------------


class RollbackTargetMismatch(RemediationError):
    """The target no longer looks the way the recorded plan expects.

    Refused, never applied anyway. A plan written against twelve replicas
    applied to a workload somebody has since taken to two is not a rollback; it
    is a second unreviewed change, made under the authority of the first.
    """

    def __init__(self, plan_id: str, target: str, *, expected: str, observed: str) -> None:
        super().__init__(
            f"{target!r} no longer matches the state {plan_id!r} was recorded against "
            f"(expected {expected[:12]}…, found {observed[:12]}…), so the rollback is "
            f"refused rather than applied to something it was not written for."
        )
        self.plan_id = plan_id
        self.target = target
        self.expected = expected
        self.observed = observed


class RollbackWindowClosed(RemediationError):
    """The configured window for one-click rollback has passed."""

    def __init__(self, plan_id: str, *, window_seconds: float) -> None:
        super().__init__(
            f"{plan_id!r} is outside its {window_seconds:g}s rollback window. Reversing it "
            f"now is a new change, and goes through a fresh approval against fresh state."
        )
        self.plan_id = plan_id
        self.window_seconds = window_seconds


class RollbackFailed(RemediationError):
    """A rollback ran and did not achieve what it said it would.

    Raised loudly and never retried automatically. A failed rollback needs human
    judgement, not more automation: the second attempt is being made against a
    system that is now in a state nobody designed.
    """

    def __init__(self, plan_id: str, *, completed: Sequence[int], detail: str) -> None:
        ran = ", ".join(str(step) for step in completed) or "none"
        super().__init__(
            f"The rollback {plan_id!r} did not complete: {detail} Steps that ran: {ran}. "
            f"This is not retried automatically — the system is now in a state nobody "
            f"planned, and the next move is a person's."
        )
        self.plan_id = plan_id
        self.completed = tuple(completed)
        self.detail = detail


# --- Wiring ------------------------------------------------------------------


class UnknownRemediationCapability(RemediationError):
    """Something asked for a capability this deployment has no components for.

    Every remediation capability declares four: a state reader, an applier, a
    rollback generator, and a verifier. A capability registered with fewer is a
    capability that could execute without a plan, so the gap is refused here
    rather than discovered halfway through an incident.
    """

    def __init__(self, capability: str, *, known: Sequence[str] = ()) -> None:
        listed = ", ".join(sorted(known)) or "none"
        super().__init__(
            f"No remediation components are registered for {capability!r}. "
            f"This deployment has: {listed}."
        )
        self.capability = capability
        self.known = tuple(known)


__all__ = [
    "ApprovalRefused",
    "ConditionsNotMet",
    "KillSwitchEngaged",
    "NoRollbackPlan",
    "RemediationError",
    "RollbackFailed",
    "RollbackTargetMismatch",
    "RollbackWindowClosed",
    "TargetLocked",
    "UnknownRemediationCapability",
]
