"""A past decision reconstructs the exact diff that was approved.

The question this answers is asked months later, usually by somebody who was
not in the room: *what did the person who approved this actually see?* An audit
record that names the change and points at the target answers a different
question — what the target says now — and the two diverge the moment anybody
edits it again.

So the diff is retained on the record, filtered through the guardrail
engine first. A reviewer looking at a proposed value that turned out to contain
a credential must not have that credential preserved forever in the one table
nobody may delete from.

Every stage is audited, not just the decision. A change that was queued
and never answered is a fact about how the queue is working, and a conflict is
the moment the system noticed reality had moved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from config.constants.security import (
    APPROVAL_AUDIT_ACTION_CONFLICT,
    APPROVAL_AUDIT_ACTION_EXPIRE,
    APPROVAL_AUDIT_ACTION_QUEUE,
    APPROVAL_AUDIT_RESOURCE_KIND_CHANGE,
    AUDIT_DETAIL_CHANGE_TYPE,
    AUDIT_DETAIL_DIFF,
    AUDIT_DETAIL_REAL_PRINCIPAL,
    AUDIT_DETAIL_TARGET,
)
from platform.approvals.errors import ChangeConflicted
from platform.approvals.service import ApprovalService
from platform.identity.audit.recorder import APPROVAL_AUDIT_ACTION_DECIDE, AuditRecorder
from platform.persistence.ports import PersistenceGateway, TenantScope

pytestmark = pytest.mark.unit

REQUESTER = "ada"
REVIEWER = "grace"

Applier = Any


async def events_of(gateway: PersistenceGateway, scope: TenantScope) -> list[Any]:
    """Return every audit event stored for the organisation, oldest first."""
    async with gateway.begin(scope) as uow:
        return list(await uow.audit.query())


async def actions_of(gateway: PersistenceGateway, scope: TenantScope) -> list[str]:
    """Return the action names of every stored audit event."""
    return [event.action for event in await events_of(gateway, scope)]


@pytest.fixture
def audited_service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: Applier,
    clock: Any,
) -> ApprovalService:
    """Return a service that writes its records to the in-memory audit trail."""
    from platform.approvals.models import ChangeType

    return ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        recorder=AuditRecorder(gateway=gateway, clock=clock),
        clock=clock,
    )


async def queue_one(service: ApprovalService, target: Callable[..., Any]) -> Any:
    """Queue one prompt change through ``service``."""
    from platform.approvals.models import ChangeType

    return await service.queue(
        change_type=ChangeType.PROMPT,
        target=target(),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="the regulator asked for it",
    )


async def test_queueing_a_change_is_audited(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    target: Callable[..., Any],
) -> None:
    change = await queue_one(audited_service, target)

    events = await events_of(gateway, scope)
    queued = [event for event in events if event.action == APPROVAL_AUDIT_ACTION_QUEUE]

    assert len(queued) == 1
    assert queued[0].resource_kind == APPROVAL_AUDIT_RESOURCE_KIND_CHANGE
    assert queued[0].resource_id == change.change_id
    assert queued[0].detail[AUDIT_DETAIL_REAL_PRINCIPAL] == REQUESTER


async def test_a_decision_is_audited_with_both_principals(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    target: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """The record carries the requester and the approver, not one of them."""
    change = await queue_one(audited_service, target)

    await audited_service.decide(change.change_id, **as_reviewer(), approve=True)

    decided = [
        event
        for event in await events_of(gateway, scope)
        if event.action == APPROVAL_AUDIT_ACTION_DECIDE
    ]
    assert len(decided) == 1
    assert decided[0].detail[AUDIT_DETAIL_REAL_PRINCIPAL] == REVIEWER
    assert decided[0].detail["requester"] == REQUESTER


async def test_the_audit_record_reconstructs_the_diff_that_was_approved(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: Applier,
    target: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Stated exactly: the diff survives the target moving on afterwards."""
    change = await queue_one(audited_service, target)
    shown = await audited_service.review(change.change_id)

    await audited_service.decide(change.change_id, **as_reviewer(), approve=True)

    applier.state = {"level": "off"}  # the world moves on
    await audited_service.queue(
        change_type=change.change_type,
        target=target(),
        proposed={"level": "standard"},
        requester=REQUESTER,
        rationale="another change entirely",
    )

    decided = next(
        event
        for event in await events_of(gateway, scope)
        if event.action == APPROVAL_AUDIT_ACTION_DECIDE
    )
    assert decided.detail[AUDIT_DETAIL_DIFF] == shown.diff.to_record()
    assert decided.detail[AUDIT_DETAIL_CHANGE_TYPE] == change.change_type.value
    assert decided.detail[AUDIT_DETAIL_TARGET] == str(change.target)


async def test_a_rejection_retains_its_reason_and_its_diff(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    target: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_one(audited_service, target)

    await audited_service.decide(
        change.change_id, **as_reviewer(), approve=False, reason="the level was chosen on purpose"
    )

    decided = next(
        event
        for event in await events_of(gateway, scope)
        if event.action == APPROVAL_AUDIT_ACTION_DECIDE
    )
    assert decided.detail["reason"] == "the level was chosen on purpose"
    assert decided.detail["approved"] is False
    assert AUDIT_DETAIL_DIFF in decided.detail


async def test_a_conflict_is_audited_when_it_is_detected(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: Applier,
    target: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """The moment the system noticed reality had moved is worth a record."""
    change = await queue_one(audited_service, target)
    applier.state = {"level": "off"}

    with pytest.raises(ChangeConflicted):
        await audited_service.decide(change.change_id, **as_reviewer(), approve=True)

    assert APPROVAL_AUDIT_ACTION_CONFLICT in await actions_of(gateway, scope)


async def test_an_expiry_is_audited(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    target: Callable[..., Any],
    clock: Any,
) -> None:
    await queue_one(audited_service, target)
    clock.advance(days=30)

    await audited_service.expire_due()

    assert APPROVAL_AUDIT_ACTION_EXPIRE in await actions_of(gateway, scope)


async def test_a_secret_in_a_proposed_value_never_reaches_the_record(
    audited_service: ApprovalService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    target: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Article IV: the diff passes the guardrail engine before display and audit.

    The audit table is the one nobody may delete from. A credential preserved
    there is preserved for the retention period, and the refusal that put it
    there was supposed to be keeping it out.
    """
    from platform.approvals.models import ChangeType

    secret = "AKIAIOSFODNN7EXAMPLE"
    change = await audited_service.queue(
        change_type=ChangeType.CONFIGURATION,
        target=target(path="integrations.aws.key"),
        proposed={"integrations": {"aws": {"key": secret}}},
        requester=REQUESTER,
        rationale="pasted by mistake",
    )

    await audited_service.decide(change.change_id, **as_reviewer(), approve=False, reason="no")

    for event in await events_of(gateway, scope):
        assert secret not in repr(event.detail)
