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


async def test_an_undecided_request_can_be_amended(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A review that outlives the state it was raised against has to record that.

    A change queued on Monday and approved on Wednesday may have to note that
    the target moved in between, and be re-raised against what the target says
    now. Neither is a decision, and neither should mean discarding the request.
    """
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())

        amended = await uow.approvals.amend_request(
            "a-1", arguments={"namespace": "prod", "deployment": "checkout", "conflict": "stale"}
        )

    assert amended.arguments["conflict"] == "stale"
    assert amended.state is ApprovalState.PENDING


async def test_an_amendment_leaves_everything_but_the_arguments_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        original = await uow.approvals.create_request(request_for())
        amended = await uow.approvals.amend_request("a-1", arguments={"replaced": True})

    assert amended.requested_at == original.requested_at
    assert amended.expires_at == original.expires_at
    assert amended.action == original.action
    assert amended.summary == original.summary


async def test_a_decided_request_cannot_be_amended(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Rewriting the call after somebody approved it changes what they approved."""
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for())
        await uow.approvals.store_rollback_plan(plan_for())
        await approve(uow)

        with pytest.raises(AppendOnlyViolation):
            await uow.approvals.amend_request("a-1", arguments={"deployment": "something-else"})


async def test_amending_an_unknown_request_names_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.approvals.amend_request("a-nothing", arguments={})


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


async def test_decided_requests_come_back_most_recently_answered_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A decision is evidence, so there has to be a way to read the decisions.

    Ordered by when it was answered rather than by when it was asked: the queue
    that recalls "what was said the last three times" wants the last three
    things said, and the two orders differ whenever a proposal waited.
    """
    async with gateway.begin(scope) as uow:
        for identifier, minutes in (("a-first", 0.0), ("a-second", 1.0)):
            await uow.approvals.create_request(request_for(identifier, minutes=minutes))
            await uow.approvals.store_rollback_plan(plan_for(identifier))

        await uow.approvals.decide(
            "a-second", state=ApprovalState.APPROVED, decided_by="u-ada", decided_at=at(5)
        )
        await uow.approvals.decide(
            "a-first", state=ApprovalState.REJECTED, decided_by="u-ada", decided_at=at(9)
        )
        # Still waiting, so still absent from a listing of what was answered.
        await uow.approvals.create_request(request_for("a-open", minutes=2))

        decided = await uow.approvals.list_decided()

    assert [item.approval_id for item in decided] == ["a-first", "a-second"]
    assert decided[0].reason is None
    assert decided[0].state is ApprovalState.REJECTED


async def test_decided_requests_can_be_narrowed_to_one_action(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The queue reads one kind of decision, not every approval the org ever made."""
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request_for("a-restart"))
        await uow.approvals.store_rollback_plan(plan_for("a-restart"))
        await approve(uow, "a-restart")

        other = ApprovalRequest(
            approval_id="a-proposal",
            run_id="run-2",
            action="detector.proposal",
            side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
            summary="Enable the corpus quorum check.",
            requested_at=at(1),
            expires_at=at(60),
        )
        await uow.approvals.create_request(other)
        await uow.approvals.store_rollback_plan(plan_for("a-proposal"))
        await uow.approvals.decide(
            "a-proposal", state=ApprovalState.APPROVED, decided_by="u-ada", decided_at=at(7)
        )

        found = await uow.approvals.list_decided(action="detector.proposal")

    assert [item.approval_id for item in found] == ["a-proposal"]
