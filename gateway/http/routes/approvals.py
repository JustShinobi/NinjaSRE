"""Approvals as a reviewer has to see them, and the rollback that follows one.

An approval card that shows only "restart checkout?" is a card nobody can
answer. Article III's requirement is that a change above read carries a stored
rollback plan *before* it can be approved, so the plan already exists by the
time anybody is looking — and returning it with the request is what turns the
decision from a guess into a review.

Everything here is a read except the rollback, which is the one action a
reviewer takes after the fact rather than before it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.state import GatewayState
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    RollbackPlan,
)

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


class RollbackStepView(BaseModel):
    ordinal: int
    description: str
    capability: str
    arguments: dict[str, Any]


class RollbackPlanView(BaseModel):
    plan_id: str
    approval_id: str
    steps: list[RollbackStepView]
    notes: str | None = None


class ApprovalView(BaseModel):
    approval_id: str
    run_id: str
    action: str
    side_effect_level: str
    summary: str
    requested_at: str
    expires_at: str
    state: str
    arguments: dict[str, Any]
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None
    #: ``None`` rather than an omitted field: "there is no plan" is information a
    #: reviewer needs, and a missing key reads as "not loaded".
    rollback_plan: RollbackPlanView | None = None


class ApprovalList(BaseModel):
    approvals: list[ApprovalView]


class RollbackResult(BaseModel):
    plan_id: str
    approval_id: str
    executed_at: str
    completed_steps: list[int]


def _plan_view(plan: RollbackPlan | None) -> RollbackPlanView | None:
    if plan is None:
        return None
    return RollbackPlanView(
        plan_id=plan.plan_id,
        approval_id=plan.approval_id,
        steps=[
            RollbackStepView(
                ordinal=step.ordinal,
                description=step.description,
                capability=step.capability,
                arguments=dict(step.arguments),
            )
            for step in plan.steps
        ],
        notes=plan.notes,
    )


def _view(request: ApprovalRequest, plan: RollbackPlan | None) -> ApprovalView:
    return ApprovalView(
        approval_id=request.approval_id,
        run_id=request.run_id,
        action=request.action,
        side_effect_level=request.side_effect_level,
        summary=request.summary,
        requested_at=request.requested_at.isoformat(),
        expires_at=request.expires_at.isoformat(),
        state=request.state.value,
        arguments=dict(request.arguments),
        decided_at=request.decided_at.isoformat() if request.decided_at else None,
        decided_by=request.decided_by,
        reason=request.reason,
        rollback_plan=_plan_view(plan),
    )


@router.get("", response_model=ApprovalList)
async def list_approvals(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    run_id: str = "",
    limit: int = 50,
) -> ApprovalList:
    """Return undecided approvals, longest-waiting first (FR-008).

    Each carries its rollback plan, because the queue is where a reviewer
    decides which one to open — and "this one has no undo" is exactly the fact
    that decides it.
    """
    async with state.gateway.begin(auth.scope) as uow:
        pending = await uow.approvals.list_pending(run_id=run_id or None, limit=limit)
        plans = {
            request.approval_id: await uow.approvals.rollback_plan_for(request.approval_id)
            for request in pending
        }
    return ApprovalList(
        approvals=[_view(request, plans[request.approval_id]) for request in pending]
    )


@router.get("/{approval_id}", response_model=ApprovalView)
async def get_approval(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ApprovalView:
    """Return one approval with everything a decision rests on (FR-009)."""
    async with state.gateway.begin(auth.scope) as uow:
        request = await uow.approvals.get_request(approval_id)
        if request is None:
            raise not_found(f"no approval {approval_id!r}")
        plan = await uow.approvals.rollback_plan_for(approval_id)
    return _view(request, plan)


@router.post("/{approval_id}/rollback", response_model=RollbackResult)
async def record_rollback(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RollbackResult:
    """Record that the stored rollback plan for ``approval_id`` was executed (FR-011).

    Refused for an approval that was never granted. Undoing something nobody
    authorised is not a rollback, and recording one would put a step in the
    audit trail that never had a decision behind it.
    """
    executed_at = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        request = await uow.approvals.get_request(approval_id)
        if request is None:
            raise not_found(f"no approval {approval_id!r}")
        if request.state.value != "approved":
            raise bad_request(
                f"{approval_id!r} is {request.state.value}, so there is nothing to roll back"
            )
        plan = await uow.approvals.rollback_plan_for(approval_id)
        if plan is None:
            raise not_found(f"no rollback plan is stored for {approval_id!r}")
        completed = [step.ordinal for step in plan.steps]
        recorded = await uow.approvals.record_rollback_executed(
            plan.plan_id, executed_at=executed_at, completed_steps=completed
        )
    return RollbackResult(
        plan_id=recorded.plan_id,
        approval_id=approval_id,
        executed_at=executed_at.isoformat(),
        completed_steps=completed,
    )


__all__ = ["router"]
