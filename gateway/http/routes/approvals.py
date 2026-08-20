"""Approvals as a reviewer has to see them, the decision, and the rollback.

An approval card that shows only "restart checkout?" is a card nobody can
answer. Article III's requirement is that a change above read carries a stored
rollback plan *before* it can be approved, so the plan already exists by the
time anybody is looking — and returning it with the request is what turns the
decision from a guess into a review.

Deciding is the one write here that is not the rollback. It calls
``ApprovalStore.decide`` directly rather than routing through the governance
``ApprovalService`` or the agent ``ProposalQueue``: both exist for a different
shape of change (a configuration edit, a detector, a knowledge write, a
prompt), neither claims a remediation approval as one of its own, and neither
executes anything on approval — recording the decision is genuinely all this
route does. Nothing above read is invoked from here; carrying that out is a
separate mechanism this feature does not wire in.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.security import (
    APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
    REMEDIATION_PAYLOAD_BLAST_RADIUS,
)
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, conflict, not_found
from gateway.http.state import GatewayState
from platform.approvals.models import PROPOSED_KEY
from platform.identity.audit.recorder import (
    APPROVAL_AUDIT_ACTION_DECIDE,
    AuditContext,
    AuditRecorder,
)
from platform.persistence.errors import AppendOnlyViolation, RecordNotFound
from platform.persistence.ports import ActorKind, AuditOutcome
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
)

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])

#: A verdict this route recognises. Anything else is refused before a store is
#: ever asked.
_VERDICTS = frozenset({"approve", "reject"})


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
    #: How many resources the *action* itself would reach, from the topology
    #: graph — not how many subjects the incident carries, which is a different
    #: number answering a different question. ``None`` when nothing computed
    #: one for this request, which today is every request: never a fabricated
    #: count standing in for a real one.
    blast_radius_count: int | None = None


class ApprovalList(BaseModel):
    approvals: list[ApprovalView]


class RollbackResult(BaseModel):
    plan_id: str
    approval_id: str
    executed_at: str
    completed_steps: list[int]


class ApprovalDecisionRequest(BaseModel):
    verdict: str
    #: Required to reject, ignored on an approval — the same rule the
    #: proposal queue's own decision route enforces, restated here because
    #: this route calls a different store method and cannot inherit the check.
    reason: str = Field(default="")


class ApprovalDecisionResult(BaseModel):
    approval_id: str
    state: str
    decided_at: str
    decided_by: str


def _blast_radius_count(arguments: Mapping[str, Any]) -> int | None:
    """Return the action's own blast-radius count, when the request carries one.

    A remediation queued through the approval service nests its payload under
    ``proposed`` (``platform.approvals.models.PendingChange.to_arguments``); a
    request written directly carries it flat. Both are read so a caller does
    not have to know which one produced this row. ``None`` — never a
    fabricated zero — when neither shape names a count.
    """
    proposed = arguments.get(PROPOSED_KEY)
    nested = (
        proposed.get(REMEDIATION_PAYLOAD_BLAST_RADIUS) if isinstance(proposed, Mapping) else None
    )
    flat = arguments.get(REMEDIATION_PAYLOAD_BLAST_RADIUS)
    radius = (
        nested if isinstance(nested, Mapping) else (flat if isinstance(flat, Mapping) else None)
    )
    if radius is None:
        return None
    count = radius.get("count")
    return count if isinstance(count, int) and not isinstance(count, bool) else None


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
        blast_radius_count=_blast_radius_count(request.arguments),
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


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResult)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ApprovalDecisionResult:
    """Approve or reject an approval request, in the caller's name.

    Approving records the decision, the decider and the instant, and nothing
    else: this route never invokes the capability the approval names. The
    store itself refuses to record an approval with no stored rollback plan
    (Article III), so that guarantee does not depend on this handler getting
    the order right — there is no order to get wrong, because there is no
    write to a plan here at all, only a read of one that already exists.

    Rejecting without a reason is refused before either store is touched. The
    console's own control disables the reject button until a reason is typed;
    this is the rule behind that courtesy.
    """
    if body.verdict not in _VERDICTS:
        raise bad_request(f"{body.verdict!r} is not a verdict; use 'approve' or 'reject'")
    if body.verdict == "reject" and not body.reason.strip():
        raise bad_request(
            "a rejection carries a reason. The same proposal arrives again after the "
            "next investigation of the same failure, and the reason is what stops it."
        )

    decided_at = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        existing = await uow.approvals.get_request(approval_id)
        if existing is None:
            raise not_found(f"no approval {approval_id!r}")
        try:
            decided = await uow.approvals.decide(
                approval_id,
                state=ApprovalState.APPROVED
                if body.verdict == "approve"
                else ApprovalState.REJECTED,
                decided_by=auth.principal_id,
                decided_at=decided_at,
                reason=body.reason or None,
            )
        except RecordNotFound as missing:
            # Reached only when approving and no rollback plan is stored — the
            # approval itself was already confirmed to exist, above. A missing
            # precondition, not a missing resource: 400, not 404, and
            # distinguishable from "no such route" for exactly that reason.
            raise bad_request(str(missing)) from missing
        except AppendOnlyViolation as already_decided:
            raise conflict(str(already_decided)) from already_decided

    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=APPROVAL_AUDIT_ACTION_DECIDE,
        resource_kind=APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
        resource_id=approval_id,
        outcome=AuditOutcome.ALLOWED if body.verdict == "approve" else AuditOutcome.DENIED,
        detail={
            "action": decided.action,
            "summary": decided.summary,
            "reason": decided.reason,
        },
    )

    return ApprovalDecisionResult(
        approval_id=decided.approval_id,
        state=decided.state.value,
        decided_at=decided.decided_at.isoformat() if decided.decided_at else "",
        decided_by=decided.decided_by or "",
    )


__all__ = ["router"]
