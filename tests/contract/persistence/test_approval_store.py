"""Contract: approvals, and the rollback plan Article III requires beside them."""

from __future__ import annotations

import pytest
from conftest import at

from config.constants.security import SIDE_EFFECT_WRITE_REVERSIBLE
from platform.persistence.errors import AppendOnlyViolation, RecordNotFound
from platform.persistence.ports import (
    ApprovalRequest,
    ApprovalState,
    PersistenceGateway,
    RollbackPlan,
    RollbackStep,
    TenantScope,
    UnitOfWork,
)

pytestmark = pytest.mark.contract


def request_for(approval_id: str = "a-1", *, minutes: float = 0.0) -> ApprovalRequest:
    """Return a pending approval request."""
    return ApprovalRequest(
        approval_id=approval_id,
        run_id="run-1",
        action="kubernetes.restart_deployment",
        side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
        summary="Restart the checkout deployment.",
        requested_at=at(minutes),
        expires_at=at(minutes + 30),
        arguments={"namespace": "prod", "deployment": "checkout"},
    )


def plan_for(approval_id: str = "a-1") -> RollbackPlan:
    """Return a rollback plan for an approval."""
    return RollbackPlan(
        plan_id=f"p-{approval_id}",
        approval_id=approval_id,
        steps=(
            RollbackStep(
                ordinal=0,
                description="Scale back to the previous replica count.",
                capability="kubernetes.scale_deployment",
                arguments={"replicas": 4},
            ),
        ),
    )


async def approve(uow: UnitOfWork, approval_id: str = "a-1") -> ApprovalRequest:
    """Approve a request, with its rollback plan already stored."""
    return await uow.approvals.decide(
        approval_id,
        state=ApprovalState.APPROVED,
        decided_by="u-ada",
        decided_at=at(5),
    )


async def test_an_approval_cannot_be_granted_without_a_rollback_plan(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Article III's "and", enforced rather than trusted.

    A deployment cannot reach a state where something irreversible was
    authorised and nobody wrote down how to undo it.
    """
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())

        with pytest.raises(RecordNotFound):
            await approve(uow)


async def test_an_approval_with_a_plan_is_granted(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        await uow.approvals.store_rollback_plan(plan_for())
        decided = await approve(uow)

    assert decided.state is ApprovalState.APPROVED
    assert decided.decided_by == "u-ada"


async def test_a_rejection_needs_no_plan(gateway: PersistenceGateway, scope: TenantScope) -> None:
    # Nothing happened, so there is nothing to undo.
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        decided = await uow.approvals.decide(
            "a-1",
            state=ApprovalState.REJECTED,
            decided_by="u-ada",
            decided_at=at(5),
            reason="Wrong namespace.",
        )

    assert decided.state is ApprovalState.REJECTED
    assert decided.reason == "Wrong namespace."


async def test_a_decision_is_made_once(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        await uow.approvals.store_rollback_plan(plan_for())
        await approve(uow)

        with pytest.raises(AppendOnlyViolation):
            await uow.approvals.decide(
                "a-1",
                state=ApprovalState.REJECTED,
                decided_by="u-someone-else",
                decided_at=at(9),
            )


async def test_the_undo_cannot_be_rewritten_after_it_was_approved(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Rewriting the rollback procedure after somebody approved the action
    # changes what they approved.
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        await uow.approvals.store_rollback_plan(plan_for())
        await approve(uow)

        with pytest.raises(AppendOnlyViolation):
            await uow.approvals.store_rollback_plan(plan_for())


async def test_the_longest_waiting_request_is_listed_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for("a-late", minutes=10))
        await uow.approvals.create_request(request_for("a-early", minutes=0))
        pending = await uow.approvals.list_pending()

    assert [item.approval_id for item in pending] == ["a-early", "a-late"]


async def test_an_expired_request_cannot_be_answered_later(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The operator clicking it an hour later has forgotten what the cluster
    # looked like.
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        expired = await uow.approvals.expire_due(at(31))

        assert [item.approval_id for item in expired] == ["a-1"]
        assert await uow.approvals.list_pending() == ()

        # Expired is decided. There is no path back to pending.
        with pytest.raises(AppendOnlyViolation):
            await approve(uow)


async def test_a_partial_rollback_is_recorded_as_partial(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The normal case when something has gone wrong twice. Knowing which steps
    # completed is the difference between a safe retry and a second incident.
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        await uow.approvals.store_rollback_plan(plan_for())
        await approve(uow)
        recorded = await uow.approvals.record_rollback_executed(
            "p-a-1", executed_at=at(20), completed_steps=[0]
        )

    assert recorded.notes is not None
    assert "1 of 1" in recorded.notes
