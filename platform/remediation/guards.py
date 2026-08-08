"""The three things the closed loop knows that stop the next unattended action.

Feature 040 gave the gate a policy engine and four bounds no level overrides.
These are three more, and they are here rather than there because all three are
facts this package learned by acting: that a rollback failed on this resource,
that this capability has already been applied here four times, and that this
capability's effect is not something anybody can measure.

All three **downgrade to approval** rather than refusing outright, and the
distinction is the point. Every one of them is a reason for the deployment to
stop deciding on its own; none of them is a reason a person may not act. A
suspended resource is precisely the one somebody has to be able to fix, and a
recurring problem is closed by a change that a human makes.

The order is severity. A suspension means nobody knows what state the resource
is in; a recurrence means the deployment is repeating itself; an unverifiable
action means it would act and never find out. An operator reading the first
needs to read it first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.remediation.components import ComponentRegistry
from platform.remediation.models import RemediationAction
from platform.remediation.obligations import resource_of
from platform.remediation.recurrence import problem_key
from platform.remediation.suspension import AutonomySuspensions

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Guard:
    """Whether the closed loop lets this run unattended, and why not if it does not.

    ``PERMITTED`` is a value rather than ``None`` so a caller reads one shape.
    ``reason`` is never empty when ``permitted`` is false, because the reason is
    what the approval request shows a reviewer and what the model is told —
    "waiting on a human" is true and useless, and "waiting because the last
    rollback on this resource failed" is what somebody acts on.
    """

    permitted: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.permitted and not self.reason.strip():
            raise ValueError(
                "A guard that refuses must say why. An unexplained downgrade leaves a "
                "reviewer approving something with no idea what the deployment knew."
            )


#: Nothing the closed loop knows stops this. A shared value, so the ordinary
#: path allocates nothing and every caller compares against the same thing.
PERMITTED: Guard = Guard()


@runtime_checkable
class AutonomyGuards(Protocol):
    """What the gate asks the closed loop before acting without a human."""

    async def check(self, action: RemediationAction) -> Guard:
        """Return whether ``action`` may run unattended, and why not if it may not."""


@dataclass(slots=True)
class ClosedLoopGuards:
    """The suspensions, the recurring problems, and the unverifiable capabilities.

    Opens its own unit of work, because it is asked on the gate's path and the
    gate holds no transaction — the same shape ``AuditSpendLedger`` uses for the
    same reason.

    ``allow_unverifiable`` comes from the deployment's autonomy policy rather
    than being a constant here. FR-006 says whether an unverifiable action may
    run unattended is a policy decision and not a default; the default this
    package ships is the strict reading of silence, which is what a deployment
    that has decided nothing should get.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    registry: ComponentRegistry
    allow_unverifiable: bool = False

    async def check(self, action: RemediationAction) -> Guard:
        """Return whether the closed loop lets ``action`` run unattended."""
        resource_id = resource_of(action)

        async with self.gateway.begin(self.scope) as uow:
            suspension = await AutonomySuspensions(audit=uow.audit).current(resource_id)
            problem = await uow.remediation.open_problem_for(
                problem_key(action.capability, resource_id)
            )

        if suspension is not None:
            _LOG.warning(
                "remediation.guard_suspended",
                action_id=action.action_id,
                capability=action.capability,
                resource_id=resource_id,
            )
            return Guard(
                permitted=False,
                reason=(
                    f"autonomous action on {resource_id} is suspended since "
                    f"{suspension.since.isoformat()} — {suspension.reason} A person has to "
                    f"clear the suspension before this deployment acts unattended here."
                ),
            )

        if problem is not None and problem.suppressing:
            _LOG.warning(
                "remediation.guard_recurrence",
                action_id=action.action_id,
                capability=action.capability,
                resource_id=resource_id,
                problem_id=problem.problem_id,
            )
            return Guard(
                permitted=False,
                reason=(
                    f"{action.capability} has already been applied to {resource_id} "
                    f"{problem.occurrences} times inside the declared window, so it is a "
                    f"recurring problem ({problem.problem_id}) rather than an incident. "
                    f"Autonomous repetition is suppressed until that problem is closed by "
                    f"a change."
                ),
            )

        declaration = self.registry.verification_of(action.capability)
        if not declaration.verifiable and not self.allow_unverifiable:
            return Guard(
                permitted=False,
                reason=(
                    f"{action.capability} declares no signal its effect would appear in "
                    f"({declaration.reason}), and this deployment has not decided that "
                    f"unverifiable actions may run unattended."
                ),
            )

        return PERMITTED


__all__ = [
    "PERMITTED",
    "AutonomyGuards",
    "ClosedLoopGuards",
    "Guard",
]
