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


# --- Refusals after the change ------------------------------------------------


class UndeclaredVerification(RemediationError):
    """A capability said nothing about how anybody would know it worked.

    Not the same as declaring itself unverifiable, which is a legitimate answer
    with a reason attached. This is the absence of any answer, and it is refused
    at construction because the alternative is a capability that reports
    ``inconclusive`` forever and reads exactly like one whose effect is
    genuinely hard to measure.
    """

    def __init__(self) -> None:
        super().__init__(
            "A verification declaration needs either the signals the effect appears in "
            "or a reason there are none. Use VerificationDeclaration.unverifiable(reason) "
            "to say the effect has no signal — the reason is what makes that a decision "
            "somebody made rather than a field nobody filled in."
        )


class UnknownVerificationSignal(RemediationError):
    """A capability declared a signal no source in this deployment produces.

    Refused at registration. A capability verifying against a signal nothing
    emits reads ``inconclusive`` every time, forever, and the failure is
    invisible: it looks like a system whose effects are hard to measure rather
    than like a wiring mistake.
    """

    def __init__(self, signal: str, *, known: Sequence[str] = ()) -> None:
        listed = ", ".join(known) or "none"
        super().__init__(
            f"No source in this deployment produces {signal!r}, so a verification "
            f"against it could never conclude anything. This deployment emits: {listed}."
        )
        self.signal = signal
        self.known = tuple(known)


class VerificationNotOwed(RemediationError):
    """Something tried to verify an action that has no obligation recorded.

    Raised rather than treated as "nothing to do". An obligation that vanished
    between the execution and the sweep is a lost verification, and a system
    that shrugged at one would report the action as awaiting verification until
    somebody noticed by hand.
    """

    def __init__(self, action_id: str) -> None:
        super().__init__(
            f"No verification obligation is recorded for {action_id!r}. Every execution "
            f"writes one before its run ends, so its absence means either the write "
            f"failed or something is verifying an action this deployment did not take."
        )
        self.action_id = action_id


class UnknownRecurringProblem(RemediationError):
    """Something asked to close a pattern this deployment has never raised.

    Its own type rather than the unknown-capability one, because the next step
    differs: an unknown capability is a wiring mistake, and an unknown problem
    identifier is somebody working from a stale listing.
    """

    def __init__(self, problem_id: str) -> None:
        super().__init__(
            f"No recurring problem called {problem_id!r} has been raised in this "
            f"deployment. Recurring problems are listed alongside the incidents, and "
            f"one that has already been closed keeps its identifier."
        )
        self.problem_id = problem_id


class AutonomySuspended(RemediationError):
    """A rollback failed here, and nothing autonomous runs until a human says so.

    The strongest refusal this package has, and deliberately narrow: it is per
    resource, it names the action that caused it, and it is cleared by a person
    rather than by a timeout. At the point it is raised the deployment has
    changed something, failed to undo it, and does not know what state the
    resource is in — continuing to act on it unattended is the worst available
    option.
    """

    def __init__(self, resource_id: str, *, since: str = "", reason: str = "") -> None:
        when = f" since {since}" if since else ""
        why = f": {reason}" if reason else "."
        super().__init__(
            f"Autonomous action on {resource_id!r} is suspended{when}{why} A person has "
            f"to clear the suspension before this deployment acts on it unattended "
            f"again. An approved action from a human is still permitted."
        )
        self.resource_id = resource_id
        self.since = since
        self.reason = reason


class RecurrenceSuppressed(RemediationError):
    """This has been done here enough times that repeating it is not the answer.

    Raised where an autonomous repetition would have happened, and not where a
    human's approval would. The recurring problem it names is closed by a change
    — more disk, a rotation, a fixed leak — and suppressing the repetition is
    what stops the deployment from being an efficient way to avoid making one.
    """

    def __init__(self, capability: str, resource_id: str, *, problem_id: str = "") -> None:
        named = f" ({problem_id})" if problem_id else ""
        super().__init__(
            f"{capability!r} has already been applied to {resource_id!r} enough times "
            f"inside the declared window to have raised a recurring problem{named}. "
            f"Autonomous repetition is suppressed until that problem is closed by a "
            f"change; a human may still approve one."
        )
        self.capability = capability
        self.resource_id = resource_id
        self.problem_id = problem_id


__all__ = [
    "ApprovalRefused",
    "AutonomySuspended",
    "ConditionsNotMet",
    "KillSwitchEngaged",
    "NoRollbackPlan",
    "RecurrenceSuppressed",
    "RemediationError",
    "RollbackFailed",
    "RollbackTargetMismatch",
    "RollbackWindowClosed",
    "TargetLocked",
    "UndeclaredVerification",
    "UnknownRecurringProblem",
    "UnknownRemediationCapability",
    "UnknownVerificationSignal",
    "VerificationNotOwed",
]
