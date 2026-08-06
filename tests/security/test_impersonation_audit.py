"""An impersonated action records both principals, for every action type.

Impersonation is the feature that most obviously trades accountability for
support capability, and the trade is only acceptable if the accountability half
is total. "Total" here means: not one audited action class records the
impersonated context and loses the human behind it, and not one records the
human and loses the context they were acting in.

So the suite is parameterised over the whole action vocabulary rather than over
a sample. A new action class added without a dual-principal path fails here,
which is the only way this property survives the fifteen features that will add
audited actions after this one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import (
    AUDIT_DETAIL_BREAK_GLASS,
    AUDIT_DETAIL_IMPERSONATED_NODE,
    AUDIT_DETAIL_IMPERSONATED_PRINCIPAL,
    AUDIT_DETAIL_REAL_PRINCIPAL,
    AUDIT_DETAIL_SOURCE_ADDRESS,
    IMPERSONATION_MAX_DURATION_SECONDS,
)
from platform.identity.audit.recorder import AUDITED_ACTIONS, AuditContext, AuditRecorder
from platform.identity.impersonation import Impersonation
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope

pytestmark = pytest.mark.security

ORG = "acme"
ADMIN = "erin"
TEAM = "payments"
SUBJECT = "payments-lead"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
SOURCE = "203.0.113.7"


def impersonation() -> Impersonation:
    """Return a live admin context switch into the payments team."""
    return Impersonation(
        real_principal_id=ADMIN,
        node_id=TEAM,
        subject_principal_id=SUBJECT,
        reason="reproducing the report the payments team filed",
        started_at=AT,
        expires_at=AT + timedelta(seconds=IMPERSONATION_MAX_DURATION_SECONDS),
    )


def context() -> AuditContext:
    """Return the acting context an impersonating admin carries."""
    return AuditContext(
        actor_kind=ActorKind.USER,
        actor_id=ADMIN,
        impersonation=impersonation(),
        source_address=SOURCE,
    )


def recorder() -> AuditRecorder:
    """Return a recorder with a fixed clock and no storage behind it."""
    return AuditRecorder(gateway=FakePersistence(), clock=lambda: AT)


@pytest.mark.parametrize("action", AUDITED_ACTIONS)
def test_every_audited_action_records_both_principals(action: str) -> None:
    """Both principals, across the whole vocabulary rather than across a sample."""
    event = recorder().event(
        context(),
        action=action,
        resource_kind="thing",
        resource_id="thing-1",
    )

    assert event.actor_id == ADMIN, "the real human must be the actor, not the context"
    assert event.detail[AUDIT_DETAIL_REAL_PRINCIPAL] == ADMIN
    assert event.detail[AUDIT_DETAIL_IMPERSONATED_PRINCIPAL] == SUBJECT
    assert event.detail[AUDIT_DETAIL_IMPERSONATED_NODE] == TEAM


@pytest.mark.parametrize("action", AUDITED_ACTIONS)
def test_every_audited_action_records_the_mandatory_fields(action: str) -> None:
    """Principal, timestamp, action, target, outcome, and source address."""
    event = recorder().event(
        context(),
        action=action,
        resource_kind="thing",
        resource_id="thing-1",
        outcome=AuditOutcome.DENIED,
    )

    assert event.event_id
    assert event.occurred_at == AT
    assert event.actor_kind is ActorKind.USER
    assert event.action == action
    assert event.resource_kind == "thing"
    assert event.resource_id == "thing-1"
    assert event.outcome is AuditOutcome.DENIED
    assert event.detail[AUDIT_DETAIL_SOURCE_ADDRESS] == SOURCE


def test_an_ordinary_action_carries_no_impersonation_keys() -> None:
    """An unimpersonated record is not padded with nulls a query has to exclude."""
    plain = AuditContext(actor_kind=ActorKind.USER, actor_id="ada", source_address=SOURCE)
    event = recorder().event(
        plain, action="config.set", resource_kind="config_node", resource_id="x"
    )

    assert event.detail[AUDIT_DETAIL_REAL_PRINCIPAL] == "ada"
    assert AUDIT_DETAIL_IMPERSONATED_PRINCIPAL not in event.detail
    assert AUDIT_DETAIL_IMPERSONATED_NODE not in event.detail


def test_a_break_glass_action_is_flagged_as_well_as_attributed() -> None:
    """Break-glass use is prominent, not merely present."""
    opened = AuditContext(
        actor_kind=ActorKind.USER,
        actor_id="break-glass",
        break_glass=True,
        source_address=SOURCE,
    )
    event = recorder().event(
        opened, action="config.set", resource_kind="config_node", resource_id="x"
    )

    assert event.detail[AUDIT_DETAIL_BREAK_GLASS] is True


def test_impersonation_and_break_glass_are_recorded_together() -> None:
    """The worst case for a reviewer is the one that must not lose a field."""
    both = AuditContext(
        actor_kind=ActorKind.USER,
        actor_id=ADMIN,
        impersonation=impersonation(),
        break_glass=True,
        source_address=SOURCE,
    )
    event = recorder().event(
        both, action="config.set", resource_kind="config_node", resource_id="x"
    )

    assert event.detail[AUDIT_DETAIL_BREAK_GLASS] is True
    assert event.detail[AUDIT_DETAIL_IMPERSONATED_PRINCIPAL] == SUBJECT


def test_a_caller_supplied_detail_cannot_overwrite_the_attribution() -> None:
    """Attribution is not a field a caller gets to set.

    A record whose ``real_principal_id`` came from the request body is a record
    an attacker writes. The context wins, always.
    """
    event = recorder().event(
        context(),
        action="config.set",
        resource_kind="config_node",
        resource_id="x",
        detail={AUDIT_DETAIL_REAL_PRINCIPAL: "somebody-else", "field": "policies.masking.level"},
    )

    assert event.detail[AUDIT_DETAIL_REAL_PRINCIPAL] == ADMIN
    assert event.detail["field"] == "policies.masking.level"


def test_the_action_vocabulary_covers_every_class_the_specification_names() -> None:
    """The required list, asserted as a set rather than trusted as a comment."""
    domains = {action.split(".", 1)[0] for action in AUDITED_ACTIONS}
    assert {
        "auth",
        "token",
        "config",
        "credential",
        "approval",
        "remediation",
        "impersonation",
        "permission",
    } <= domains


async def test_a_recorded_event_reaches_storage_unchanged() -> None:
    """The builder and the write path agree, so the assertions above are about
    what is stored rather than about what is constructed."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    scope = TenantScope(org_id=ORG)
    written = await AuditRecorder(gateway=gateway, clock=lambda: AT).record(
        scope,
        context(),
        action="config.set",
        resource_kind="config_node",
        resource_id="payments",
    )

    async with gateway.begin(scope) as uow:
        stored = await uow.audit.get(written.event_id)

    assert stored == written
    assert stored is not None
    assert stored.detail[AUDIT_DETAIL_IMPERSONATED_PRINCIPAL] == SUBJECT
