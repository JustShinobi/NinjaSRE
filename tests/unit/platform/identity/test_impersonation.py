"""An admin in a team's context: permitted, bounded, and never anonymous."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.identity import impersonation
from platform.identity.audit.recorder import AuditContext
from platform.identity.authorisation import PermissionSet
from platform.identity.errors import ImpersonationRejected, PermissionDenied
from platform.identity.impersonation import MAX_IMPERSONATION, Impersonation
from platform.identity.models import Grant, Principal
from platform.identity.permissions import Role
from platform.persistence.ports import ActorKind

ORG = "acme"
ADMIN = "erin"
TEAM = "payments"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
REASON = "reproducing the report the payments team filed"


def admin() -> Principal:
    """Return the admin doing the support work."""
    return Principal(principal_id=ADMIN, org_id=ORG, display_name="Erin")


def held(role: Role = Role.ADMIN, node_id: str | None = None) -> PermissionSet:
    """Return what the admin holds, at ``node_id``."""
    return PermissionSet(
        grants=(Grant(grant_id="g1", principal_id=ADMIN, role=role, node_id=node_id),)
    )


def test_an_admin_may_take_a_team_context() -> None:
    """The ordinary case, which is the reason this exists."""
    live = impersonation.begin(admin(), held(), node_id=TEAM, reason=REASON, clock=lambda: AT)

    assert live.real_principal_id == ADMIN
    assert live.node_id == TEAM
    assert live.is_live(AT)


def test_an_operator_may_not() -> None:
    """The permission is checked like any other, so the same rules apply."""
    with pytest.raises(PermissionDenied):
        impersonation.begin(
            admin(), held(Role.OPERATOR), node_id=TEAM, reason=REASON, clock=lambda: AT
        )


def test_an_admin_scoped_elsewhere_may_not_support_this_team() -> None:
    """The check happens at the node, not organisation-wide.

    An admin of one division supporting a team in another would be an admin
    whose scope stopped meaning anything the moment support was involved.
    """
    with pytest.raises(PermissionDenied):
        impersonation.begin(
            admin(),
            held(Role.ADMIN, node_id="platform"),
            node_id=TEAM,
            reason=REASON,
            clock=lambda: AT,
        )


def test_an_impersonation_ends_by_itself() -> None:
    """A forgotten context switch is not a standing privilege."""
    live = impersonation.begin(admin(), held(), node_id=TEAM, reason=REASON, clock=lambda: AT)

    assert live.is_live(AT + MAX_IMPERSONATION - timedelta(minutes=1))
    assert not live.is_live(AT + MAX_IMPERSONATION)


def test_an_expired_impersonation_refuses_to_be_used() -> None:
    """Presenting a lapsed one is an error rather than a quiet downgrade."""
    live = impersonation.begin(admin(), held(), node_id=TEAM, reason=REASON, clock=lambda: AT)

    with pytest.raises(ImpersonationRejected):
        live.require_live(AT + MAX_IMPERSONATION)


def test_a_longer_impersonation_than_the_ceiling_is_refused() -> None:
    """The ceiling is not a default a caller talks past."""
    with pytest.raises(ImpersonationRejected):
        impersonation.begin(
            admin(),
            held(),
            node_id=TEAM,
            reason=REASON,
            duration=MAX_IMPERSONATION + timedelta(minutes=1),
            clock=lambda: AT,
        )


def test_a_shorter_impersonation_is_allowed() -> None:
    """Asking for less than the ceiling is the behaviour to encourage."""
    live = impersonation.begin(
        admin(),
        held(),
        node_id=TEAM,
        reason=REASON,
        duration=timedelta(minutes=5),
        clock=lambda: AT,
    )
    assert live.remaining(AT) == timedelta(minutes=5)


def test_an_impersonation_without_a_reason_is_refused() -> None:
    """ "Erin acted as payments" is not something a reviewer can assess."""
    with pytest.raises(ImpersonationRejected):
        impersonation.begin(admin(), held(), node_id=TEAM, reason="   ", clock=lambda: AT)


def test_an_impersonation_that_would_expire_before_it_began_is_refused() -> None:
    """Constructing an incoherent one fails where it is written."""
    with pytest.raises(ImpersonationRejected):
        Impersonation(
            real_principal_id=ADMIN,
            node_id=TEAM,
            started_at=AT,
            expires_at=AT - timedelta(minutes=1),
            reason=REASON,
        )


def test_remaining_never_goes_negative() -> None:
    """A caller rendering "expires in" should not be handed a negative duration."""
    live = impersonation.begin(admin(), held(), node_id=TEAM, reason=REASON, clock=lambda: AT)
    assert live.remaining(AT + MAX_IMPERSONATION * 2) == timedelta()


def test_acting_as_a_team_records_the_team_rather_than_inventing_a_person() -> None:
    """An admin reproducing a team-wide problem is not pretending to be anybody.

    Recording a person they never chose would make the audit trail say something
    untrue, which is worse than saying less.
    """
    live = impersonation.begin(admin(), held(), node_id=TEAM, reason=REASON, clock=lambda: AT)
    context = AuditContext(actor_kind=ActorKind.USER, actor_id=ADMIN, impersonation=live)

    detail = context.attribution()
    assert detail["impersonated_principal_id"] == TEAM
    assert detail["impersonated_node_id"] == TEAM


def test_acting_as_a_named_person_records_them() -> None:
    """When the admin did choose somebody, that is what goes on the record."""
    live = impersonation.begin(
        admin(),
        held(),
        node_id=TEAM,
        reason=REASON,
        subject_principal_id="payments-lead",
        clock=lambda: AT,
    )
    context = AuditContext(actor_kind=ActorKind.USER, actor_id=ADMIN, impersonation=live)

    assert context.attribution()["impersonated_principal_id"] == "payments-lead"


def test_the_start_and_the_end_have_actions_of_their_own() -> None:
    """ "When did Erin have this access" is not inferred from side effects."""
    assert impersonation.START_ACTION != impersonation.END_ACTION
    assert impersonation.START_ACTION.startswith("impersonation.")
    assert impersonation.END_ACTION.startswith("impersonation.")
