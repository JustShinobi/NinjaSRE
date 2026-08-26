"""The only way a gated change moves, in either direction.

Every transition in this feature happens in this file. That is not tidiness — it
is the requirement. ``decide`` is where the permission is re-checked, where the
fingerprint is compared, where the audit record is written, and where the
applier is finally called, in that order; a second path into the applied state
would be a path missing one of those four, and the missing one would not be
obvious from reading it.

``decide(approve)`` does six things and the order is load-bearing at every step:

1. **read the change**, and refuse a second decision on one already decided —
   two reviewers clicking at once is routine, and the second must be told what
   the first decided rather than have their click discarded;
2. **re-check permission**, against what the deciding principal holds *now* and
   not what they held when the change was queued;
3. **refuse self-approval** unless policy allows it, reading the real principal
   as well as the presented one, so impersonation is not the way around it;
4. **re-check the policy**, because it may have tightened since the change was
   queued and a change that could not legally be written must not be legally
   approvable;
5. **compare the fingerprint**, and mark the change conflicted rather than apply
   it against state the reviewer never saw;
6. **record the decision, then apply, then publish** — in that order, so a crash
   between the record and the application leaves a change that says it was
   approved and was not, which is the direction an operator can investigate. The
   reverse would leave a change that applied with no record of anybody
   authorising it.

**Queueing refuses what could never be approved.** A change that violates a
policy maximum is not parked in somebody's review list to be rejected later; it
is refused at the queue, where the person who wrote it is still looking at it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    APPROVAL_AUDIT_ACTION_CONFLICT,
    APPROVAL_AUDIT_ACTION_EXPIRE,
    APPROVAL_AUDIT_ACTION_QUEUE,
    APPROVAL_AUDIT_RESOURCE_KIND_CHANGE,
    AUDIT_DETAIL_CHANGE_TYPE,
    AUDIT_DETAIL_DIFF,
    AUDIT_DETAIL_TARGET,
    AUDIT_DETAIL_TARGET_FINGERPRINT,
    MAX_PENDING_CHANGES_LISTED,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.approvals.blast_radius import BlastRadius
from platform.approvals.blast_radius import compute as compute_radius
from platform.approvals.closure import ClosurePublisher, DecisionEvent
from platform.approvals.diff.engine import DiffEngine, StructuredDiff
from platform.approvals.diff.renderers import RENDERERS
from platform.approvals.diff.summarise import DiffSummary, summarise
from platform.approvals.errors import (
    ChangeAlreadyDecided,
    ChangeConflicted,
    ChangeExpired,
    ChangeNotFound,
    ReviewerNotPermitted,
    SelfApprovalForbidden,
)
from platform.approvals.models import (
    ChangeState,
    ChangeTarget,
    ChangeType,
    Conflict,
    ConflictReason,
    Decision,
    PendingChange,
    ReviewerSet,
    fingerprint_of,
)
from platform.approvals.notification import ReviewerNotifier
from platform.approvals.policy import DEFAULT_POLICY, SecurityPolicy
from platform.approvals.routing import may_decide, reviewers_for
from platform.approvals.state_machine import advance, require_transition
from platform.config_service.hierarchy import Hierarchy
from platform.identity.audit.recorder import (
    APPROVAL_AUDIT_ACTION_DECIDE,
    AuditContext,
    AuditRecorder,
)
from platform.identity.authorisation import PermissionSet
from platform.identity.models import Grant, Principal
from platform.observability.logging import get_logger
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import (
    ActorKind,
    AuditOutcome,
    PersistenceGateway,
    RollbackPlan,
    RollbackStep,
    TenantScope,
)

_LOG = get_logger(__name__)

#: The capability a rollback step names when undoing a queued change means
#: restoring what the target said before. Article III requires a stored plan
#: before anything may be approved, and for these five change types the plan is
#: always the same shape: put the previous value back.
RESTORE_CAPABILITY = "approvals.restore"


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@runtime_checkable
class ChangeApplier(Protocol):
    """How one change type reads its target and writes to it.

    Two methods rather than one, because the read is needed three times — at
    queue time to fingerprint, at decision time to compare, and at re-review to
    re-fingerprint — and only one of those is followed by a write.

    ``read`` returns ``None`` for a target that no longer exists. That is
    distinct from an empty mapping, which is a target that exists and holds
    nothing, and the difference decides whether a conflict can be recovered.
    """

    async def read(
        self, target: ChangeTarget, *, proposed: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any] | None:
        """Return the target's current value, or ``None`` if it is gone.

        ``proposed`` is the change being queued, for an applier whose target
        cannot be named by a string. A configuration path names a field and a
        knowledge document names itself, so three of the four appliers ignore
        it. A hypervisor guest is addressed by a node, a number and a kind, and
        an applier handed only ``name@environment`` has to guess two of the
        three — which is how a conflict check ends up raising inside the call
        that creates the approval.
        """

    async def apply(self, change: PendingChange) -> None:
        """Apply ``change``'s proposed value to its target."""


@dataclass(frozen=True, slots=True)
class ChangeReview:
    """Everything a reviewer is shown, assembled once.

    Assembled together rather than fetched piecemeal by a surface, because the
    three parts have to describe the same moment. A console that read the diff,
    then the blast radius, then the reviewer set would render three views of a
    tree that may have been reshaped in between.
    """

    change: PendingChange
    diff: StructuredDiff
    summary: DiffSummary
    blast_radius: BlastRadius
    reviewers: ReviewerSet

    @property
    def is_reviewable(self) -> bool:
        """Return whether anybody can act on this review as it stands."""
        return self.change.is_open and not self.reviewers.is_empty

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of what was shown."""
        return {
            "change_id": self.change.change_id,
            "diff": self.diff.to_record(),
            "summary": self.summary.to_record(),
            "blast_radius": self.blast_radius.to_record(),
            "reviewers": list(self.reviewers.reviewers),
        }


@dataclass(slots=True)
class ApprovalService:
    """Queue, review, decide, expire — for every gated change type there is."""

    gateway: PersistenceGateway
    scope: TenantScope
    appliers: Mapping[ChangeType, ChangeApplier]
    policy: SecurityPolicy = DEFAULT_POLICY
    recorder: AuditRecorder | None = None
    notifier: ReviewerNotifier | None = None
    closure: ClosurePublisher | None = None
    diffs: DiffEngine = field(default_factory=lambda: DiffEngine(renderers=RENDERERS))
    clock: Callable[[], datetime] = _utc_now
    identifiers: Callable[[], str] = lambda: str(uuid.uuid4())

    # --- Queueing ------------------------------------------------------------

    async def queue(
        self,
        *,
        change_type: ChangeType,
        target: ChangeTarget,
        proposed: Mapping[str, Any],
        requester: str,
        rationale: str,
        side_effect_level: str = SIDE_EFFECT_WRITE_REVERSIBLE,
        expiry_hours: float | None = None,
        context: AuditContext | None = None,
    ) -> PendingChange:
        """Queue a change against ``target``'s current state, and return it.

        The policy is checked *before* anything is stored. A change that could
        never legally be approved has no business occupying a reviewer's queue,
        and refusing it here puts the refusal in front of the person who wrote
        it rather than in front of somebody reviewing it two days later.

        The rollback plan is written in the same transaction as the request.
        The store refuses to record an approval for a request with no plan —
        Article III's "and" made structural — so writing it here is what makes
        the change approvable at all, and doing both in one unit of work is what
        stops a crash leaving a change nobody can decide.

        ``expiry_hours`` narrows the organisation's window for one change and
        never widens it. A production remediation is answered on incident
        timescales rather than on the days a prompt change gets, and an approval
        that outlived the incident would apply to a system nobody reviewed it
        against. A caller asking for longer than the policy allows gets the
        policy's number, because the window is the organisation's decision.
        """
        self.policy.check_settings(proposed)

        at = self.clock()
        current = await self._read(change_type, target, proposed=proposed)
        change = PendingChange.queued(
            change_id=self.identifiers(),
            change_type=change_type,
            target=target,
            proposed=proposed,
            current=current,
            requester=requester,
            rationale=rationale,
            at=at,
            expiry_hours=(
                min(expiry_hours, self.policy.change_expiry_hours)
                if expiry_hours is not None
                else self.policy.change_expiry_hours
            ),
            side_effect_level=side_effect_level,
        )

        async with self.gateway.begin(self.scope) as uow:
            await uow.approvals.create_request(change.to_request())
            await uow.approvals.store_rollback_plan(self._rollback_plan(change, at=at))

        await self._audit(
            change,
            action=APPROVAL_AUDIT_ACTION_QUEUE,
            context=context if context is not None else self._context(requester),
            detail={"rationale": rationale},
        )
        await self._notify(change)

        _LOG.info(
            "approvals.queued",
            change_id=change.change_id,
            change_type=change_type.value,
            target=str(target),
            requester=requester,
        )
        return change

    # --- Reading -------------------------------------------------------------

    async def get(self, change_id: str) -> PendingChange:
        """Return the queued change with ``change_id``, or raise naming it."""
        async with self.gateway.begin(self.scope) as uow:
            request = await uow.approvals.get_request(change_id)
        if request is None:
            raise ChangeNotFound(change_id)
        return PendingChange.of_request(request)

    async def list_open(
        self, *, limit: int = MAX_PENDING_CHANGES_LISTED
    ) -> tuple[PendingChange, ...]:
        """Return every change still waiting on somebody, longest-waiting first.

        Conflicted changes are included. They are undecided, somebody still has
        to answer them, and a queue that hid them would be a queue where a
        conflicted change waited until it expired.
        """
        async with self.gateway.begin(self.scope) as uow:
            pending = await uow.approvals.list_pending(limit=limit)
        return tuple(PendingChange.of_request(request) for request in pending)

    async def review(self, change_id: str) -> ChangeReview:
        """Return everything a reviewer is shown for ``change_id``.

        The blast radius is computed before the diff is rendered and is meant to
        be displayed above it. The stakes decide how carefully somebody reads a
        diff, and a reviewer who learns the scope afterwards has already decided
        how much attention to spend.
        """
        change = await self.get(change_id)
        diff = self.diffs.diff(change.change_type, change.current, change.proposed)

        hierarchy, grants = await self._tree_and_grants()
        return ChangeReview(
            change=change,
            diff=diff,
            summary=summarise(diff),
            blast_radius=compute_radius(hierarchy, change.node_id, path=change.target.path),
            reviewers=reviewers_for(change, grants, policy=self.policy, hierarchy=hierarchy),
        )

    # --- Deciding ------------------------------------------------------------

    async def decide(
        self,
        change_id: str,
        *,
        approver: Principal,
        permissions: PermissionSet,
        approve: bool,
        reason: str | None = None,
        context: AuditContext | None = None,
    ) -> PendingChange:
        """Approve or reject ``change_id``, and return it as decided.

        Every refusal here leaves the change where it was, except a detected
        conflict — which moves it to ``conflicted`` on purpose, because the
        divergence is a fact about the change and not about the attempt to
        decide it. A reviewer who retries gets the same refusal rather than a
        different one.
        """
        change = await self.get(change_id)
        self._require_undecided(change)
        self._require_unexpired(change)
        self._require_permitted(change, approver, permissions, context)

        if not approve:
            return await self._reject(change, approver, reason, context)

        self._require_not_self_approved(change, approver, context)
        self.policy.check_settings(change.proposed)
        await self._require_unconflicted(change, context)

        return await self._approve(change, approver, reason, context)

    async def rereview(self, change_id: str) -> PendingChange:
        """Put a conflicted change back into review against current state.

        Re-fingerprinted against what the target says *now*, and its stored
        "current" replaced with it. Leaving either behind would put the change
        straight back into conflict on the next decision, and would show the
        next reviewer a diff against state nobody has.

        A deleted target cannot be re-reviewed. There is nothing to apply the
        change to, and re-reviewing it would produce an approval that could
        never be honoured.
        """
        change = await self.get(change_id)
        if change.conflict is not None and not change.conflict.is_recoverable:
            raise ChangeConflicted(
                change.change_id, change.conflict.reason.value, change.conflict.detail
            )

        require_transition(change, ChangeState.PENDING)
        observed = await self._read(change.change_type, change.target, proposed=change.proposed)
        rereviewed = change.rereviewed(against=observed, at=self.clock())
        return await self._amend(rereviewed)

    async def expire_due(self, now: datetime | None = None) -> tuple[PendingChange, ...]:
        """Close every change whose answering window has passed.

        Closed, never applied. A change nobody answered during the incident must
        not still be answerable a week later, when the operator clicking it has
        forgotten what the system looked like when it was proposed.
        """
        at = now if now is not None else self.clock()
        async with self.gateway.begin(self.scope) as uow:
            lapsed = await uow.approvals.expire_due(at)

        expired = tuple(PendingChange.of_request(request) for request in lapsed)
        for change in expired:
            await self._audit(
                change,
                action=APPROVAL_AUDIT_ACTION_EXPIRE,
                context=self._context(change.requester),
                outcome=AuditOutcome.DENIED,
                detail={"expired_at": at.isoformat()},
            )
        await self._publish_all(expired, at=at)
        return expired

    # --- The guards ----------------------------------------------------------

    def _require_undecided(self, change: PendingChange) -> None:
        """Raise unless ``change`` is still waiting on somebody."""
        if change.state.is_decided:
            raise ChangeAlreadyDecided(
                change.change_id,
                change.state.value,
                change.decision.decided_by if change.decision else None,
            )

    def _require_unexpired(self, change: PendingChange) -> None:
        """Raise unless ``change``'s answering window is still open.

        Asked of the clock rather than of the stored state. A lapsed change is
        relabelled ``expired`` by ``expire_due``, and a deployment that has not
        scheduled that sweep would otherwise leave every lapsed change
        answerable for ever — which is not hypothetical: it is how a
        remediation proposed with a fifteen-minute window came to be approved
        and carried out fifty minutes after the reading behind it stopped being
        current.

        Refused before the permission check, because "this window closed" is
        true for everyone and telling a reviewer they lack a permission would
        send them to ask for one that would not have helped.
        """
        now = self.clock()
        if change.has_expired(now):
            raise ChangeExpired(change.change_id, change.expires_at.isoformat(), now.isoformat())

    def _require_permitted(
        self,
        change: PendingChange,
        approver: Principal,
        permissions: PermissionSet,
        context: AuditContext | None,
    ) -> None:
        """Raise unless ``approver`` may decide ``change`` right now.

        Applies to rejections too. Rejecting is a decision, and somebody with no
        standing at the node must not be able to make one — a stranger who could
        reject changes could stop a team's work as effectively as one who could
        approve them.
        """
        if not approver.is_active or not may_decide(
            change, permissions, principal_id=approver.principal_id
        ):
            self._log_denial(change, approver, context)
            raise ReviewerNotPermitted(change.change_id, approver.principal_id, change.node_id)

    def _require_not_self_approved(
        self, change: PendingChange, approver: Principal, context: AuditContext | None
    ) -> None:
        """Raise unless somebody other than the requester is approving.

        Both principals are checked. The presented one catches an admin acting
        *as* the requester; the real one catches the requester hiding behind
        somebody else. A control an impersonation steps around is not one.
        """
        if self.policy.permits_self_approval():
            return
        acting = {approver.principal_id}
        if context is not None:
            acting.add(context.actor_id)
        if change.requester in acting:
            raise SelfApprovalForbidden(change.change_id, change.requester)

    async def _require_unconflicted(
        self, change: PendingChange, context: AuditContext | None
    ) -> None:
        """Mark ``change`` conflicted and raise if the target has moved."""
        observed = await self._read(change.change_type, change.target, proposed=change.proposed)
        if observed is None:
            await self._conflict(
                change,
                ConflictReason.TARGET_DELETED,
                f"the target {change.target} no longer exists.",
                observed=None,
                context=context,
            )
        if change.state is ChangeState.CONFLICTED:
            conflict = change.conflict
            raise ChangeConflicted(
                change.change_id,
                conflict.reason.value if conflict else ConflictReason.TARGET_CHANGED.value,
                conflict.detail if conflict else "it was marked conflicted and not re-reviewed.",
            )
        if not change.matches(observed):
            await self._conflict(
                change,
                ConflictReason.TARGET_CHANGED,
                f"the target {change.target} changed after this was queued.",
                observed=observed,
                context=context,
            )

    async def _conflict(
        self,
        change: PendingChange,
        reason: ConflictReason,
        detail: str,
        *,
        observed: Mapping[str, Any] | None,
        context: AuditContext | None,
    ) -> None:
        """Store ``change`` as conflicted, audit it, and raise saying why."""
        marked = change.conflicting(
            Conflict(
                reason=reason,
                detected_at=self.clock(),
                detail=detail,
                expected_fingerprint=change.fingerprint,
                observed_fingerprint=fingerprint_of(observed),
            )
        )
        require_transition(change, ChangeState.CONFLICTED)
        await self._amend(marked)
        await self._audit(
            marked,
            action=APPROVAL_AUDIT_ACTION_CONFLICT,
            context=context if context is not None else self._context(change.requester),
            outcome=AuditOutcome.DENIED,
            detail={"conflict": marked.conflict.to_record() if marked.conflict else {}},
        )
        raise ChangeConflicted(change.change_id, reason.value, detail)

    # --- The two decisions ---------------------------------------------------

    async def _approve(
        self,
        change: PendingChange,
        approver: Principal,
        reason: str | None,
        context: AuditContext | None,
    ) -> PendingChange:
        """Record the approval, apply the change, then close it everywhere.

        Record before apply. A crash in between leaves a change that says it was
        approved and was not, which an operator can find and re-run; the reverse
        leaves a change that applied with nothing saying anybody authorised it,
        which is indistinguishable from a compromise.
        """
        at = self.clock()
        decided = change.decided(
            Decision(approved=True, decided_by=approver.principal_id, decided_at=at, reason=reason)
        )
        require_transition(change, ChangeState.APPROVED)
        stored = await self._record_decision(decided)

        await self.appliers[change.change_type].apply(stored)
        await self._conflict_siblings(stored, context)
        await self._audit_decision(stored, approver, context)
        await self._publish(stored, at=at)

        _LOG.info(
            "approvals.approved",
            change_id=stored.change_id,
            change_type=stored.change_type.value,
            target=str(stored.target),
            requester=stored.requester,
            approver=approver.principal_id,
        )
        return stored

    async def _reject(
        self,
        change: PendingChange,
        approver: Principal,
        reason: str | None,
        context: AuditContext | None,
    ) -> PendingChange:
        """Discard the change, keeping the reason for the requester."""
        at = self.clock()
        decided = change.decided(
            Decision(approved=False, decided_by=approver.principal_id, decided_at=at, reason=reason)
        )
        require_transition(change, ChangeState.REJECTED)
        stored = await self._record_decision(decided)

        await self._audit_decision(stored, approver, context)
        await self._publish(stored, at=at)

        _LOG.info(
            "approvals.rejected",
            change_id=stored.change_id,
            target=str(stored.target),
            requester=stored.requester,
            approver=approver.principal_id,
            reason=reason,
        )
        return stored

    async def _conflict_siblings(
        self, approved: PendingChange, context: AuditContext | None
    ) -> None:
        """Mark every other open change to the same target conflicted.

        Not applied on top of each other, and not silently dropped. Each sibling
        was proposed against state the approval has just replaced, and its
        author is entitled to re-review it against what the target says now.
        """
        for sibling in await self.list_open():
            if sibling.change_id == approved.change_id:
                continue
            if sibling.target.identifier != approved.target.identifier:
                continue
            if sibling.state is not ChangeState.PENDING:
                continue
            marked = sibling.conflicting(
                Conflict(
                    reason=ConflictReason.SIBLING_APPROVED,
                    detected_at=self.clock(),
                    detail=(
                        f"{approved.change_id} was approved for the same target first, so "
                        f"this was queued against a value that no longer applies."
                    ),
                    expected_fingerprint=sibling.fingerprint,
                    observed_fingerprint=fingerprint_of(approved.proposed),
                )
            )
            await self._amend(marked)
            await self._audit(
                marked,
                action=APPROVAL_AUDIT_ACTION_CONFLICT,
                context=context if context is not None else self._context(sibling.requester),
                outcome=AuditOutcome.DENIED,
                detail={"superseded_by": approved.change_id},
            )

    # --- Storage -------------------------------------------------------------

    async def _record_decision(self, decided: PendingChange) -> PendingChange:
        """Write the decision and its payload, and return the change as stored.

        Two writes in one transaction. The store owns the decided state, the
        decider, and the timestamp; the payload owns everything about the change
        the store has no column for. Splitting them across transactions would
        leave a decided request whose payload still reads pending.
        """
        request = decided.to_request()
        async with self.gateway.begin(self.scope) as uow:
            await uow.approvals.amend_request(decided.change_id, arguments=decided.to_arguments())
            stored = await uow.approvals.decide(
                decided.change_id,
                state=request.state,
                decided_by=request.decided_by or "",
                decided_at=request.decided_at or self.clock(),
                reason=request.reason,
            )
        return PendingChange.of_request(stored)

    async def _amend(self, change: PendingChange) -> PendingChange:
        """Write a still-open change's payload back, and return it as stored."""
        async with self.gateway.begin(self.scope) as uow:
            stored = await uow.approvals.amend_request(
                change.change_id, arguments=change.to_arguments()
            )
        return PendingChange.of_request(stored)

    def _rollback_plan(self, change: PendingChange, *, at: datetime) -> RollbackPlan:
        """Return how approving ``change`` would be undone.

        The same shape for all five types: put back what was there. That is
        genuinely the undo for a configuration edit, a prompt change, a
        capability toggle, and a knowledge addition; feature 017 replaces it for
        remediation, where undoing a production action is not a value assignment.
        """
        return RollbackPlan(
            plan_id=f"{change.change_id}-rollback",
            approval_id=change.change_id,
            created_at=at,
            notes=(
                f"Approving this replaces {change.target} with the proposed value. Undoing it "
                f"restores what the target held when the change was queued."
            ),
            steps=(
                RollbackStep(
                    ordinal=1,
                    description=f"Restore {change.target} to its value at queue time",
                    capability=RESTORE_CAPABILITY,
                    arguments={
                        "target": change.target.identifier,
                        "path": change.target.path,
                        "value": dict(change.current),
                    },
                ),
            ),
        )

    # --- Collaborators -------------------------------------------------------

    async def _read(
        self,
        change_type: ChangeType,
        target: ChangeTarget,
        *,
        proposed: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        """Return what the target currently holds, through its own applier."""
        return await self.appliers[change_type].read(target, proposed=proposed)

    async def _tree_and_grants(self) -> tuple[Hierarchy | None, tuple[Grant, ...]]:
        """Return this tenant's tree and every grant in it, for routing.

        Both in one transaction, so the reviewer set and the blast radius
        describe the same tree. A missing tree narrows routing rather than
        widening it: without it, only exact-node and organisation-wide grants
        apply, which is the safe direction for a missing input to fail in.

        Grants are collected per principal because that is the shape the store
        offers, and the shape it offers is the one the *hot* path needs — a
        permission check reads one principal's bindings, and this is the only
        caller that wants all of them.
        """
        async with self.gateway.begin(self.scope) as uow:
            try:
                root = await uow.config.root()
            except RecordNotFound:
                return None, ()

            nodes = [root]
            frontier = [root.node_id]
            while frontier:
                for child in await uow.config.children(frontier.pop()):
                    nodes.append(child)
                    frontier.append(child.node_id)

            grants: list[Grant] = []
            for user in await uow.identity.list_users():
                grants.extend(
                    Grant.of_binding(binding)
                    for binding in await uow.identity.role_bindings_for_user(user.user_id)
                )

        return Hierarchy.of(nodes), tuple(grants)

    async def _notify(self, change: PendingChange) -> None:
        """Tell the eligible reviewers, if this deployment has anywhere to tell them."""
        if self.notifier is None:
            return
        review = await self.review(change.change_id)
        await self.notifier.notify(
            change, review.reviewers, diff=review.summary, radius=review.blast_radius
        )

    async def _publish(self, change: PendingChange, *, at: datetime) -> None:
        """Close the request on every surface that showed it."""
        if self.closure is None:
            return
        await self.closure.publish(DecisionEvent.of(change, at=at))

    async def _publish_all(self, changes: Sequence[PendingChange], *, at: datetime) -> None:
        """Close a batch, which is what an expiry sweep produces."""
        if self.closure is None:
            return
        await self.closure.publish_all(tuple(DecisionEvent.of(change, at=at) for change in changes))

    # --- Audit ---------------------------------------------------------------

    async def _audit_decision(
        self, change: PendingChange, approver: Principal, context: AuditContext | None
    ) -> None:
        """Record the decision with the diff that was decided about.

        The diff is retained on the record rather than recomputed from it. A
        record that pointed at the target would answer "what does this say now",
        and the question somebody asks months later is "what did the person who
        approved this actually see".
        """
        diff = self.diffs.diff(change.change_type, change.current, change.proposed)
        await self._audit(
            change,
            action=APPROVAL_AUDIT_ACTION_DECIDE,
            context=context if context is not None else self._context(approver.principal_id),
            outcome=AuditOutcome.ALLOWED if change.approved else AuditOutcome.DENIED,
            detail={
                "approved": change.approved,
                "reason": change.decision.reason if change.decision else None,
                "requester": change.requester,
                AUDIT_DETAIL_DIFF: diff.to_record(),
            },
        )

    async def _audit(
        self,
        change: PendingChange,
        *,
        action: str,
        context: AuditContext,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        """Write one record about ``change``, if this deployment records anything."""
        if self.recorder is None:
            return
        await self.recorder.record(
            self.scope,
            context,
            action=action,
            resource_kind=APPROVAL_AUDIT_RESOURCE_KIND_CHANGE,
            resource_id=change.change_id,
            outcome=outcome,
            detail={
                AUDIT_DETAIL_CHANGE_TYPE: change.change_type.value,
                AUDIT_DETAIL_TARGET: str(change.target),
                AUDIT_DETAIL_TARGET_FINGERPRINT: change.fingerprint,
                "state": change.state.value,
                **dict(detail or {}),
            },
        )

    def _context(self, principal_id: str) -> AuditContext:
        """Return the context a caller that supplied none is recorded under.

        A record still gets written. A caller that forgot to pass its context
        has produced a less informative record, not an absent one, and an absent
        record is the failure this whole feature exists to prevent.
        """
        return AuditContext(actor_kind=ActorKind.USER, actor_id=principal_id)

    def _log_denial(
        self, change: PendingChange, approver: Principal, context: AuditContext | None
    ) -> None:
        """Say that somebody tried to decide something they may not decide."""
        _LOG.warning(
            "approvals.decision_denied",
            change_id=change.change_id,
            node_id=change.node_id,
            principal_id=approver.principal_id,
            real_principal_id=context.actor_id if context is not None else approver.principal_id,
        )


def advance_to(change: PendingChange, state: ChangeState) -> PendingChange:
    """Return ``change`` in ``state``, guarded by the machine.

    A thin name over ``state_machine.advance`` so the service's own call sites
    read as transitions rather than as assignments. Exported because feature
    017's remediation path needs the same guard and must not grow its own.
    """
    return advance(change, state)


__all__ = [
    "RESTORE_CAPABILITY",
    "ApprovalService",
    "ChangeApplier",
    "ChangeReview",
    "advance_to",
]
