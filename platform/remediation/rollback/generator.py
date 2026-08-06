"""Producing the undo before the action, and refusing when there is none.

The ordering is the control, and it is the one thing in this package that is not
negotiable. A plan generated after execution is a description of what happened;
a plan generated before it is a design artefact the approver evaluated, and its
*absence* is itself a signal that the action is riskier than it looked.

So generation happens here, from the capability's own generator, against the
state that was read before anything ran — and the two outcomes are a plan or a
refusal. There is no third outcome where the action proceeds with the plan to be
worked out later, because that outcome is where every "we will add rollback
next sprint" ends up.

**A waiver is explicit, attributed, and audited.** Some actions genuinely have
no inverse: a cache clear does not put the entries back. An operator may say so
and proceed, and the record says who said so and why. That is a different thing
in kind from a plan that quietly was not produced, and keeping them
distinguishable is the whole reason the waiver is a value rather than a flag.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from platform.observability.logging import get_logger
from platform.remediation.components import ComponentRegistry
from platform.remediation.errors import NoRollbackPlan
from platform.remediation.models import (
    RemediationAction,
    RollbackPlan,
    StateSnapshot,
    utc_now,
)

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RollbackWaiver:
    """An operator's explicit acceptance that an action cannot be undone.

    Both fields are required and the reason is checked for content. "n/a" is not
    a reason, and the audit line this produces is read by somebody trying to
    understand a decision made during an incident they were not in.
    """

    granted_by: str
    reason: str

    def __post_init__(self) -> None:
        if not self.granted_by:
            raise ValueError("A rollback waiver must name the operator who granted it.")
        if len(self.reason.strip()) < _MIN_REASON_CHARS:
            raise ValueError(
                f"A rollback waiver's reason must be at least {_MIN_REASON_CHARS} characters. "
                f"The line is read by somebody reconstructing this decision later."
            )


#: Short enough that a genuine one-line reason passes, long enough that "ok"
#: does not. The same reasoning as the break-glass justification minimum.
_MIN_REASON_CHARS = 16


@dataclass(slots=True)
class PlanFactory:
    """Turns one proposed action into the plan that reverses it.

    Dispatch and nothing else. The steps come from the capability's own
    generator, because "what undoes a scale" is knowledge that belongs with the
    code that scales — a central table of undos would be a table that drifts
    from the actions it claims to reverse.
    """

    registry: ComponentRegistry
    clock: Callable[[], datetime] = utc_now
    identifiers: Callable[[], str] = field(default=lambda: str(uuid.uuid4()))

    def generate(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        waiver: RollbackWaiver | None = None,
    ) -> RollbackPlan:
        """Return the plan reversing ``action``, or raise when none is derivable.

        ``before`` is the state the plan is written against and the state it
        will be checked against when somebody applies it. Passing it rather than
        re-reading is what makes the plan and the approval describe the same
        instant.
        """
        components = self.registry.get(action.capability)
        derived = components.generator.plan(action, before=before)

        if derived is not None and derived.steps:
            return self._identified(derived, action, before)

        if waiver is None:
            _LOG.warning(
                "remediation.no_rollback_plan",
                action_id=action.action_id,
                capability=action.capability,
                target=str(action.target),
            )
            raise NoRollbackPlan(action.capability, str(action.target))

        return self._waived(action, before, waiver, derived)

    def _identified(
        self,
        plan: RollbackPlan,
        action: RemediationAction,
        before: StateSnapshot,
    ) -> RollbackPlan:
        """Return ``plan`` carrying the identity and the state it belongs to.

        A capability's generator writes the steps and the summary; it does not
        get to choose the plan identifier or the state the plan is checked
        against, because both are how this package knows the plan belongs to
        this action and this instant.
        """
        from dataclasses import replace

        return replace(
            plan,
            plan_id=plan.plan_id or self.identifiers(),
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            created_at=plan.created_at or self.clock(),
        )

    def _waived(
        self,
        action: RemediationAction,
        before: StateSnapshot,
        waiver: RollbackWaiver,
        derived: RollbackPlan | None,
    ) -> RollbackPlan:
        """Return the recorded acceptance that this action cannot be undone.

        Still a plan, still persisted, still shown to the reviewer — carrying
        whatever the capability *could* say about recovery even though it is not
        a reversal. An action with no record at all would be the one action
        nobody could audit.
        """
        summary = (
            derived.summary
            if derived is not None and derived.summary
            else f"{action.capability} on {action.target} cannot be undone."
        )
        plan = RollbackPlan(
            plan_id=self.identifiers(),
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=summary,
            steps=derived.steps if derived is not None else (),
            reversible=False,
            created_at=self.clock(),
        ).waived_by_operator(waiver.granted_by, waiver.reason)

        _LOG.warning(
            "remediation.rollback_waived",
            action_id=action.action_id,
            capability=action.capability,
            target=str(action.target),
            granted_by=waiver.granted_by,
        )
        return plan


__all__ = [
    "PlanFactory",
    "RollbackWaiver",
]
