"""In-memory approvals and rollback plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from platform.persistence.errors import (
    AppendOnlyViolation,
    DuplicateRecord,
    RecordNotFound,
)
from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.approval_store import (
    ORIGIN_APPROVAL_ID_KEY,
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
)


@dataclass(slots=True)
class FakeApprovalStore:
    """Approvals and rollback plans for one organisation."""

    org_id: str
    state: TenantState

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Store a pending request and return it.

        Refuses a second *live* request raised to replace the same expired one,
        which is PostgreSQL's partial unique index over ``(org_id,
        arguments->>'origin_approval_id') WHERE state = 'pending'`` mimicked
        here. Mimicked rather than left to the database because the two
        implementations of this port are held to one contract suite: a fake
        that accepted a row PostgreSQL refuses would let every caller above it
        be developed against a rule only half the deployments enforce, and the
        one that found out would be a production database at 3am.

        What it cannot mimic is the *race*. Two coroutines here interleave only
        where they await, and there is no lock to block the second insert on;
        the index is what closes that window, and the contract suite proves it
        against a real database rather than against this.
        """
        if request.approval_id in self.state.approvals:
            raise DuplicateRecord(kind="approval request", identifier=request.approval_id)
        origin = request.arguments.get(ORIGIN_APPROVAL_ID_KEY)
        if (
            request.state is ApprovalState.PENDING
            and origin is not None
            and await self.pending_for_origin(str(origin)) is not None
        ):
            raise DuplicateRecord(kind="live reproposal of approval", identifier=str(origin))
        check_payload(request.arguments, kind="approval arguments")
        self.state.approvals[request.approval_id] = request
        return request

    async def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Return the request with ``approval_id``, or ``None``."""
        return self.state.approvals.get(approval_id)

    async def decide(
        self,
        approval_id: str,
        *,
        state: ApprovalState,
        decided_by: str,
        decided_at: datetime,
        reason: str | None = None,
    ) -> ApprovalRequest:
        """Record a decision and return the request as stored."""
        request = self._require_request(approval_id)
        if request.state.is_decided:
            raise AppendOnlyViolation(kind="approval decision", identifier=approval_id)

        # Article III: an action above read needs approval *and* a stored
        # rollback plan. Refusing here is what makes the "and" structural — a
        # deployment cannot reach a state where something irreversible was
        # authorised and nobody wrote down how to undo it.
        if state is ApprovalState.APPROVED and approval_id not in self.state.rollback_plans:
            raise RecordNotFound(kind="rollback plan for approval", identifier=approval_id)

        decided = replace(
            request,
            state=state,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
        )
        self.state.approvals[approval_id] = decided
        return decided

    async def amend_request(
        self, approval_id: str, *, arguments: Mapping[str, Any]
    ) -> ApprovalRequest:
        """Replace an undecided request's arguments and return it as stored."""
        request = self._require_request(approval_id)
        if request.state.is_decided:
            raise AppendOnlyViolation(kind="approval arguments", identifier=approval_id)

        amended = replace(request, arguments=check_payload(arguments, kind="approval arguments"))
        self.state.approvals[approval_id] = amended
        return amended

    async def list_pending(
        self,
        *,
        run_id: str | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return undecided requests, oldest first."""
        check_limit(limit)
        matches = [
            request
            for request in self.state.approvals.values()
            if request.state is ApprovalState.PENDING
            and (run_id is None or request.run_id == run_id)
        ]
        matches.sort(key=lambda r: (r.requested_at, r.approval_id))
        return tuple(matches[:limit])

    async def pending_for_origin(self, approval_id: str) -> ApprovalRequest | None:
        """Return the undecided request raised to replace ``approval_id``, or ``None``."""
        matches = [
            request
            for request in self.state.approvals.values()
            if request.state is ApprovalState.PENDING
            and request.arguments.get(ORIGIN_APPROVAL_ID_KEY) == approval_id
        ]
        matches.sort(key=lambda r: (r.requested_at, r.approval_id))
        return matches[0] if matches else None

    async def list_decided(
        self,
        *,
        action: str | None = None,
        states: Sequence[ApprovalState] | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return answered requests, most recently decided first."""
        check_limit(limit)
        allowed = None if states is None else set(states)
        matches = [
            request
            for request in self.state.approvals.values()
            if request.state.is_decided
            and (action is None or request.action == action)
            and (allowed is None or request.state in allowed)
        ]
        # The identifier is the tiebreaker, and it is descending like the
        # instant: two rows decided in the same transaction have the same
        # timestamp, and a suite that sorted them by ascending id would read
        # them in the opposite order from PostgreSQL on those rows alone.
        matches.sort(
            key=lambda r: (r.decided_at or r.requested_at, r.approval_id),
            reverse=True,
        )
        return tuple(matches[:limit])

    async def discard(
        self,
        approval_id: str,
        *,
        discarded_by: str,
        discarded_at: datetime,
    ) -> ApprovalRequest:
        """Move ``approval_id`` to ``DISCARDED`` and return it as stored."""
        request = self._require_request(approval_id)
        if request.state in (
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
            ApprovalState.DISCARDED,
        ):
            raise AppendOnlyViolation(kind="approval discard", identifier=approval_id)

        discarded = replace(
            request,
            state=ApprovalState.DISCARDED,
            decided_by=discarded_by,
            decided_at=discarded_at,
            reason=None,
        )
        self.state.approvals[approval_id] = discarded
        return discarded

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        """Move every pending request past its expiry to ``EXPIRED``, and return them."""
        expired: list[ApprovalRequest] = []
        for approval_id, request in list(self.state.approvals.items()):
            if request.state is not ApprovalState.PENDING or request.expires_at > now:
                continue
            lapsed = replace(request, state=ApprovalState.EXPIRED, decided_at=now)
            self.state.approvals[approval_id] = lapsed
            expired.append(lapsed)
        expired.sort(key=lambda r: (r.requested_at, r.approval_id))
        return tuple(expired)

    async def store_rollback_plan(self, plan: RollbackPlan) -> RollbackPlan:
        """Store the plan for an approval and return it."""
        request = self._require_request(plan.approval_id)
        if request.state.is_decided:
            raise AppendOnlyViolation(kind="rollback plan", identifier=plan.approval_id)

        for step in plan.steps:
            check_payload(step.arguments, kind="rollback step arguments")

        stored = (
            plan if plan.created_at is not None else replace(plan, created_at=datetime.now(UTC))
        )
        self.state.rollback_plans[plan.approval_id] = stored
        return stored

    async def rollback_plan_for(self, approval_id: str) -> RollbackPlan | None:
        """Return the stored rollback plan for ``approval_id``, or ``None``."""
        return self.state.rollback_plans.get(approval_id)

    async def record_rollback_executed(
        self,
        plan_id: str,
        *,
        executed_at: datetime,
        completed_steps: Sequence[int],
    ) -> RollbackPlan:
        """Record which steps of a rollback actually ran, and return the plan."""
        plan = next(
            (p for p in self.state.rollback_plans.values() if p.plan_id == plan_id),
            None,
        )
        if plan is None:
            raise RecordNotFound(kind="rollback plan", identifier=plan_id)

        self.state.executed_rollbacks[plan_id] = tuple(completed_steps)
        executed = replace(
            plan,
            notes=(
                f"{len(completed_steps)} of {len(plan.steps)} step(s) executed "
                f"at {executed_at.isoformat()}."
            ),
        )
        self.state.rollback_plans[plan.approval_id] = executed
        return executed

    def _require_request(self, approval_id: str) -> ApprovalRequest:
        request = self.state.approvals.get(approval_id)
        if request is None:
            raise RecordNotFound(kind="approval request", identifier=approval_id)
        return request


__all__ = ["FakeApprovalStore"]
