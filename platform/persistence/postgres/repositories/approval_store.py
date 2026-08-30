"""Approvals and rollback plans over PostgreSQL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from platform.persistence.errors import (
    AppendOnlyViolation,
    DuplicateRecord,
    RecordNotFound,
)
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_utc,
    check_limit,
    translating,
    utc_now,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _to_request(row: models.Approval) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=row.approval_id,
        run_id=row.run_id,
        action=row.action,
        side_effect_level=row.side_effect_level,
        summary=row.summary,
        requested_at=as_utc(row.requested_at) or row.requested_at,
        expires_at=as_utc(row.expires_at) or row.expires_at,
        arguments=dict(row.arguments),
        state=ApprovalState(row.state),
        decided_at=as_utc(row.decided_at),
        decided_by=row.decided_by,
        reason=row.reason,
    )


def _to_plan(row: models.RollbackPlan) -> RollbackPlan:
    return RollbackPlan(
        plan_id=row.plan_id,
        approval_id=row.approval_id,
        steps=tuple(
            RollbackStep(
                ordinal=int(step["ordinal"]),
                description=str(step["description"]),
                capability=str(step["capability"]),
                arguments=dict(step.get("arguments", {})),
            )
            for step in row.steps
        ),
        created_at=as_utc(row.created_at),
        notes=row.notes,
    )


def _step_to_json(step: RollbackStep) -> dict[str, Any]:
    return {
        "ordinal": step.ordinal,
        "description": step.description,
        "capability": step.capability,
        "arguments": check_payload(step.arguments, kind="rollback step arguments"),
    }


@dataclass(slots=True)
class PostgresApprovalStore(TenantBound):
    """Approvals and rollback plans for one organisation."""

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Store a pending request and return it."""
        if await self.session.get(models.Approval, (self.org_id, request.approval_id)) is not None:
            raise DuplicateRecord(kind="approval request", identifier=request.approval_id)

        row = models.Approval(
            org_id=self.org_id,
            approval_id=request.approval_id,
            run_id=request.run_id,
            action=request.action,
            side_effect_level=request.side_effect_level,
            summary=request.summary,
            requested_at=request.requested_at,
            expires_at=request.expires_at,
            arguments=check_payload(request.arguments, kind="approval arguments"),
            state=request.state.value,
            decided_at=request.decided_at,
            decided_by=request.decided_by,
            reason=request.reason,
        )
        self.session.add(row)
        with translating(kind="approval request", identifier=request.approval_id):
            await self.session.flush()
        return _to_request(row)

    async def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Return the request with ``approval_id``, or ``None``."""
        row = await self.session.get(models.Approval, (self.org_id, approval_id))
        return _to_request(row) if row is not None else None

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
        row = await self._require_request(approval_id)
        if ApprovalState(row.state).is_decided:
            raise AppendOnlyViolation(kind="approval decision", identifier=approval_id)

        # Article III: an action above read needs approval *and* a stored
        # rollback plan. Refusing here is what makes the "and" structural — a
        # deployment cannot reach a state where something irreversible was
        # authorised and nobody wrote down how to undo it.
        if state is ApprovalState.APPROVED:
            plan = await self.session.get(models.RollbackPlan, (self.org_id, approval_id))
            if plan is None:
                raise RecordNotFound(kind="rollback plan for approval", identifier=approval_id)

        row.state = state.value
        row.decided_by = decided_by
        row.decided_at = decided_at
        row.reason = reason
        await self.session.flush()
        return _to_request(row)

    async def amend_request(
        self, approval_id: str, *, arguments: Mapping[str, Any]
    ) -> ApprovalRequest:
        """Replace an undecided request's arguments and return it as stored."""
        row = await self._require_request(approval_id)
        if ApprovalState(row.state).is_decided:
            raise AppendOnlyViolation(kind="approval arguments", identifier=approval_id)

        row.arguments = check_payload(arguments, kind="approval arguments")
        await self.session.flush()
        return _to_request(row)

    async def list_pending(
        self,
        *,
        run_id: str | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return undecided requests, oldest first."""
        check_limit(limit)
        statement = (
            select(models.Approval)
            .where(
                models.Approval.org_id == self.org_id,
                models.Approval.state == ApprovalState.PENDING.value,
            )
            .order_by(models.Approval.requested_at.asc(), models.Approval.approval_id.asc())
            .limit(limit)
        )
        if run_id is not None:
            statement = statement.where(models.Approval.run_id == run_id)

        rows = await self.session.scalars(statement)
        return tuple(_to_request(row) for row in rows)

    async def list_decided(
        self,
        *,
        action: str | None = None,
        states: Sequence[ApprovalState] | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return answered requests, most recently decided first."""
        check_limit(limit)
        statement = (
            select(models.Approval)
            .where(
                models.Approval.org_id == self.org_id,
                models.Approval.state != ApprovalState.PENDING.value,
            )
            .order_by(
                models.Approval.decided_at.desc().nullslast(),
                models.Approval.approval_id.desc(),
            )
            .limit(limit)
        )
        if action is not None:
            statement = statement.where(models.Approval.action == action)
        if states is not None:
            statement = statement.where(
                models.Approval.state.in_([state.value for state in states])
            )

        rows = await self.session.scalars(statement)
        return tuple(_to_request(row) for row in rows)

    async def discard(
        self,
        approval_id: str,
        *,
        discarded_by: str,
        discarded_at: datetime,
    ) -> ApprovalRequest:
        """Move ``approval_id`` to ``DISCARDED`` and return it as stored."""
        row = await self._require_request(approval_id)
        if ApprovalState(row.state) in (ApprovalState.APPROVED, ApprovalState.REJECTED):
            raise AppendOnlyViolation(kind="approval discard", identifier=approval_id)
        if ApprovalState(row.state) is ApprovalState.DISCARDED:
            raise AppendOnlyViolation(kind="approval discard", identifier=approval_id)

        row.state = ApprovalState.DISCARDED.value
        row.decided_by = discarded_by
        row.decided_at = discarded_at
        row.reason = None
        await self.session.flush()
        return _to_request(row)

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        """Move every pending request past its expiry to ``EXPIRED``, and return them."""
        rows = list(
            await self.session.scalars(
                select(models.Approval)
                .where(
                    models.Approval.org_id == self.org_id,
                    models.Approval.state == ApprovalState.PENDING.value,
                    models.Approval.expires_at <= now,
                )
                .order_by(models.Approval.requested_at.asc(), models.Approval.approval_id.asc())
            )
        )
        for row in rows:
            row.state = ApprovalState.EXPIRED.value
            row.decided_at = now
        await self.session.flush()
        return tuple(_to_request(row) for row in rows)

    async def store_rollback_plan(self, plan: RollbackPlan) -> RollbackPlan:
        """Store the plan for an approval and return it."""
        request = await self._require_request(plan.approval_id)
        if ApprovalState(request.state).is_decided:
            raise AppendOnlyViolation(kind="rollback plan", identifier=plan.approval_id)

        row = await self.session.get(models.RollbackPlan, (self.org_id, plan.approval_id))
        if row is None:
            row = models.RollbackPlan(org_id=self.org_id, approval_id=plan.approval_id)
            self.session.add(row)

        row.plan_id = plan.plan_id
        row.steps = [_step_to_json(step) for step in plan.steps]
        row.created_at = plan.created_at or utc_now()
        row.notes = plan.notes

        with translating(
            kind="rollback plan", identifier=plan.approval_id, referenced="approval request"
        ):
            await self.session.flush()
        return _to_plan(row)

    async def rollback_plan_for(self, approval_id: str) -> RollbackPlan | None:
        """Return the stored rollback plan for ``approval_id``, or ``None``."""
        row = await self.session.get(models.RollbackPlan, (self.org_id, approval_id))
        return _to_plan(row) if row is not None else None

    async def record_rollback_executed(
        self,
        plan_id: str,
        *,
        executed_at: datetime,
        completed_steps: Sequence[int],
    ) -> RollbackPlan:
        """Record which steps of a rollback actually ran, and return the plan."""
        row = await self.session.scalar(
            select(models.RollbackPlan).where(
                models.RollbackPlan.org_id == self.org_id,
                models.RollbackPlan.plan_id == plan_id,
            )
        )
        if row is None:
            raise RecordNotFound(kind="rollback plan", identifier=plan_id)

        row.executed_steps = as_list(completed_steps)
        row.executed_at = executed_at
        row.notes = (
            f"{len(completed_steps)} of {len(row.steps)} step(s) executed "
            f"at {executed_at.isoformat()}."
        )
        await self.session.flush()
        return _to_plan(row)

    async def _require_request(self, approval_id: str) -> models.Approval:
        row = await self.session.get(models.Approval, (self.org_id, approval_id))
        if row is None:
            raise RecordNotFound(kind="approval request", identifier=approval_id)
        return row


__all__ = ["PostgresApprovalStore"]
