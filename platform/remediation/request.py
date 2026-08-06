"""Assembling what a human is actually shown before they approve a production change.

An approval prompt that says "restart checkout-api?" is a prompt people learn to
click. What makes the decision real is everything around it: what the workload
looks like right now, what else depends on it, what would undo the change, and
what the agent saw that made it propose this. Approval fatigue is how this
control fails in practice, and the defence against it is not fewer prompts — it
is prompts that are worth reading.

So a request carries five things and refuses to be built without the first four:

* **the target and its current observed state**, read at request time so the
  fingerprint the decision is checked against describes something real;
* **the blast radius**, from the topology graph, because "this affects checkout"
  and "this affects checkout and nineteen services behind it" are different
  decisions;
* **the rollback plan**, rendered beside the action rather than behind a link —
  a step whose undo nobody read is a step approved on the assumption one exists;
* **the evidence**, because the reviewer's question is not "may this run" but
  "is this the right thing to do", and the second is unanswerable without it;
* **any conflicting action already pending on the same target**, so two people
  approving two things for one workload is something the second one sees.

**The expiry is short and the default is deny.** A configuration change may wait
three days. A remediation may not: an approval that arrives forty minutes into
an incident applies to a cluster that has already moved, and letting it lapse is
the safe direction.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.security import (
    MAX_REMEDIATION_BLAST_RADIUS_REPORTED,
    REMEDIATION_APPROVAL_EXPIRY_SECONDS,
    REMEDIATION_BLAST_RADIUS_DEPTH,
)
from platform.approvals.models import ChangeTarget, ChangeType, PendingChange
from platform.approvals.service import ApprovalService
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.remediation.components import ComponentRegistry
from platform.remediation.models import (
    RemediationAction,
    RollbackPlan,
    StateSnapshot,
    remediation_payload,
    utc_now,
)
from platform.remediation.rollback.generator import PlanFactory, RollbackWaiver

_LOG = get_logger(__name__)

#: The remediation approval window, expressed the way the approval service takes
#: it. Derived rather than written twice, so the constants tier stays the single
#: place the number is decided.
REMEDIATION_EXPIRY_HOURS = REMEDIATION_APPROVAL_EXPIRY_SECONDS / 3600


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """What an outage at the target would reach, as a reviewer reads it.

    ``known`` is not decoration. A graph nobody configured returns nothing, and
    "nothing depends on this" is the single most reassuring thing a reviewer can
    be told — so an absent answer says it is absent rather than saying zero.
    """

    origin: str
    services: tuple[str, ...] = ()
    count: int = 0
    depth: int = REMEDIATION_BLAST_RADIUS_DEPTH
    truncated: bool = False
    known: bool = True

    def describe(self) -> str:
        """Return the sentence shown above the proposed change."""
        if not self.known:
            return (
                f"The blast radius of a change to {self.origin} could not be computed: the "
                f"topology graph was not readable. Treat its scope as unknown, not small."
            )
        if not self.count:
            return f"Nothing recorded in the topology graph depends on {self.origin}."
        listed = ", ".join(self.services[:_LISTED_SERVICES])
        more = f" and {self.count - _LISTED_SERVICES} more" if self.count > _LISTED_SERVICES else ""
        return (
            f"{self.count} service(s) within {self.depth} hop(s) depend on {self.origin}: "
            f"{listed}{more}."
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form retained beside the decision."""
        return {
            "origin": self.origin,
            "services": list(self.services),
            "count": self.count,
            "depth": self.depth,
            "truncated": self.truncated,
            "known": self.known,
        }


#: How many service names the one-line description spells out before it counts.
_LISTED_SERVICES = 5


@dataclass(frozen=True, slots=True)
class RemediationRequest:
    """Everything one remediation approval is decided against.

    Built whole or not at all. A request missing its plan cannot exist, which is
    Article III's "approval *and* a stored rollback plan" expressed as a
    constructor rather than as a checklist somebody works through.
    """

    action: RemediationAction
    before: StateSnapshot
    plan: RollbackPlan
    blast_radius: BlastRadius
    conflicting: tuple[str, ...] = ()
    change_id: str = ""

    def payload(self) -> dict[str, Any]:
        """Return the approval payload, which is what the reviewer's diff renders."""
        return remediation_payload(
            self.action,
            plan=self.plan,
            blast_radius=self.blast_radius.to_record(),
        )

    def rationale(self) -> str:
        """Return the sentence that goes at the top of the review.

        Assembled here rather than by each surface. Three surfaces writing their
        own would produce three, and the one nobody reviewed would be the one
        that left out the blast radius.
        """
        parts = [self.action.intent or self.action.summary(), self.blast_radius.describe()]
        if self.plan.waived:
            parts.append(
                f"This action cannot be undone; {self.plan.waived_by or 'an operator'} "
                f"waived the rollback requirement: {self.plan.waiver_reason}"
            )
        else:
            parts.append(f"Undo: {self.plan.summary}")
        if self.conflicting:
            parts.append(
                f"{len(self.conflicting)} other change(s) are already pending on this "
                f"target and will need re-reviewing against whatever is approved first."
            )
        if self.action.evidence:
            parts.append(
                "Evidence: " + "; ".join(item.summary for item in self.action.evidence[:3])
            )
        return " ".join(parts)


@dataclass(slots=True)
class RequestBuilder:
    """Reads the world, derives the plan, and queues the approval.

    One object rather than four calls at each entry point, because the *order*
    matters and a caller that got it wrong would produce a request whose
    fingerprint described a moment before the plan was written.
    """

    registry: ComponentRegistry
    plans: PlanFactory
    approvals: ApprovalService | None = None
    gateway: PersistenceGateway | None = None
    scope: TenantScope | None = None
    depth: int = REMEDIATION_BLAST_RADIUS_DEPTH
    clock: Callable[[], datetime] = field(default=utc_now)
    identifiers: Callable[[], str] = field(default=lambda: str(uuid.uuid4()))

    async def build(
        self,
        action: RemediationAction,
        *,
        waiver: RollbackWaiver | None = None,
    ) -> RemediationRequest:
        """Return everything ``action``'s approval will be decided against.

        Raises ``NoRollbackPlan`` when nothing can be derived and no waiver was
        given, before anything is queued. A request that reached a reviewer and
        then turned out to be unapprovable would be an interruption spent on
        nothing.
        """
        at = self.clock()
        components = self.registry.get(action.capability)
        before = await components.reader.read(action, at=at)
        plan = self.plans.generate(action, before=before, waiver=waiver)
        radius = await self.blast_radius(action)
        conflicting = await self.conflicting_pending(action)

        return RemediationRequest(
            action=action,
            before=before,
            plan=plan,
            blast_radius=radius,
            conflicting=conflicting,
        )

    async def queue(
        self,
        action: RemediationAction,
        *,
        waiver: RollbackWaiver | None = None,
    ) -> RemediationRequest:
        """Build the request, queue it for a human, and return it with its identifier.

        The rollback plan reaches the store in the same transaction as the
        request — the approval store refuses to record an approval for a request
        with no plan, so queueing writes both or neither.
        """
        request = await self.build(action, waiver=waiver)
        if self.approvals is None:
            return request

        change = await self.approvals.queue(
            change_type=ChangeType.REMEDIATION,
            # ``path`` carries the capability. The approval layer's conflict
            # check re-reads the target through an applier that is handed the
            # target and nothing else, and which of the seven remediation
            # capabilities knows how to read this workload is exactly what it
            # needs. For the other four change types a path is a field within a
            # document; here it is which reader to use, and both answer the same
            # question — what part of this target is the change about.
            target=ChangeTarget(
                identifier=str(action.target),
                node_id=action.team_node_id,
                path=action.capability,
            ),
            proposed=request.payload(),
            requester=action.requester,
            rationale=request.rationale(),
            side_effect_level=action.side_effect_level.value,
            expiry_hours=REMEDIATION_EXPIRY_HOURS,
        )
        await self._store_plan(change, request.plan)

        _LOG.info(
            "remediation.approval_requested",
            action_id=action.action_id,
            change_id=change.change_id,
            capability=action.capability,
            target=str(action.target),
            blast_radius=request.blast_radius.count,
        )
        return RemediationRequest(
            action=request.action,
            before=request.before,
            plan=request.plan,
            blast_radius=request.blast_radius,
            conflicting=request.conflicting,
            change_id=change.change_id,
        )

    async def blast_radius(self, action: RemediationAction) -> BlastRadius:
        """Return what depends on the target, from the topology graph.

        Computed at request time and computed again before execution, because
        the number is the condition most likely to have changed while an
        approval waited. An unavailable graph returns *unknown* rather than
        empty, since the reassurance an empty answer gives is the one thing a
        missing input must not provide.
        """
        origin = action.target.identifier
        if self.gateway is None or self.scope is None:
            return BlastRadius(origin=origin, depth=self.depth, known=False)

        try:
            async with self.gateway.begin(self.scope) as uow:
                availability = await uow.topology.availability()
                if not availability.available:
                    return BlastRadius(origin=origin, depth=self.depth, known=False)
                found = await uow.topology.blast_radius(origin, depth=self.depth)
        except PersistenceError as failure:
            _LOG.warning(
                "remediation.blast_radius_unavailable",
                target=origin,
                error=str(failure),
            )
            return BlastRadius(origin=origin, depth=self.depth, known=False)

        services = tuple(entry.node.node_id for entry in found.reaches)
        return BlastRadius(
            origin=origin,
            services=services[:MAX_REMEDIATION_BLAST_RADIUS_REPORTED],
            count=len(services),
            depth=self.depth,
            truncated=found.truncated or len(services) > MAX_REMEDIATION_BLAST_RADIUS_REPORTED,
            known=True,
        )

    async def conflicting_pending(self, action: RemediationAction) -> tuple[str, ...]:
        """Return the open changes already queued against the same target.

        Reported rather than refused. Two engineers proposing two mitigations
        for one workload during an incident is normal and often correct; what
        must not happen is the second one being decided by somebody who did not
        know about the first.
        """
        if self.approvals is None:
            return ()
        target = str(action.target)
        return tuple(
            change.change_id
            for change in await self.approvals.list_open()
            if change.change_type is ChangeType.REMEDIATION
            and change.target.identifier == target
            and change.is_open
        )

    async def _store_plan(self, change: PendingChange, plan: RollbackPlan) -> None:
        """Replace the approval layer's generic plan with the remediation one.

        Feature 015 writes a "restore the previous value" plan for every change
        type, which is the honest undo for a configuration edit and is not one
        for a production action. Overwriting it here — while the change is still
        undecided, which is the only time the store permits it — is what makes
        the reviewer's plan and the executor's plan the same object.
        """
        if self.gateway is None or self.scope is None:
            return
        async with self.gateway.begin(self.scope) as uow:
            await uow.approvals.store_rollback_plan(plan.to_stored(change.change_id))


def evidence_summary(evidence: Sequence[Mapping[str, Any]]) -> str:
    """Return a one-line summary of the observations behind an action."""
    return "; ".join(str(item.get("summary", "")) for item in evidence if item.get("summary"))


__all__ = [
    "REMEDIATION_EXPIRY_HOURS",
    "BlastRadius",
    "RemediationRequest",
    "RequestBuilder",
    "evidence_summary",
]
