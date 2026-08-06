"""The permission catalogue and the five roles built out of it.

The assertions here are about shape rather than about any one permission. A
catalogue is right when every role is expressible in it, when no role is a
special case in code, and when the escalation order is the one the documentation
claims — and those three are what a reviewer cannot check by reading the table.
"""

from __future__ import annotations

import pytest

from platform.identity.permissions import (
    ROLE_ORDER,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    permissions_for,
)


def test_every_role_has_a_declared_permission_set() -> None:
    """No role resolves to permissions decided somewhere other than the table."""
    assert set(ROLE_PERMISSIONS) == set(Role)
    for role in Role:
        assert permissions_for(role), f"{role} would be a role that can do nothing"


def test_roles_escalate_rather_than_diverge() -> None:
    """Each role holds everything the one below it holds, and at least one more.

    Two mental models of "who may do what" is one more than an operator can hold
    during an incident. Strict nesting means a denial is always answerable with
    "you need the next role up" rather than with a matrix.
    """
    for lower, higher in zip(ROLE_ORDER, ROLE_ORDER[1:]):
        assert permissions_for(lower) < permissions_for(higher), (
            f"{higher} does not strictly contain {lower}"
        )


def test_the_owner_holds_the_whole_catalogue() -> None:
    """Nothing is grantable that no role can grant."""
    assert permissions_for(Role.OWNER) == frozenset(Permission)


def test_only_the_owner_may_end_an_organisation_or_appoint_another_owner() -> None:
    """The two powers that separate an owner from an admin."""
    admin = permissions_for(Role.ADMIN)
    assert Permission.ORG_DELETE not in admin
    assert Permission.OWNER_ASSIGN not in admin


def test_a_viewer_holds_no_permission_that_writes() -> None:
    """``viewer`` is a read role, asserted against the naming rather than a list."""
    for permission in permissions_for(Role.VIEWER):
        assert permission.is_read_only, f"{permission} is writeable and a viewer holds it"


def test_a_responder_may_run_and_approve_but_not_configure() -> None:
    """The role an on-call engineer gets: act on incidents, change nothing else."""
    responder = permissions_for(Role.RESPONDER)
    assert Permission.INVESTIGATION_RUN in responder
    assert Permission.REMEDIATION_APPROVE in responder
    assert Permission.CONFIG_WRITE not in responder


def test_an_operator_configures_and_holds_credentials_but_not_identity() -> None:
    """Managing people is an admin's job, not an operator's."""
    operator = permissions_for(Role.OPERATOR)
    assert Permission.CONFIG_WRITE in operator
    assert Permission.CREDENTIAL_WRITE in operator
    assert Permission.IDENTITY_WRITE not in operator
    assert Permission.IMPERSONATION_USE not in operator


def test_permission_values_are_namespaced() -> None:
    """Every permission reads ``domain.verb``, so an audit row sorts by domain."""
    for permission in Permission:
        domain, separator, verb = permission.value.partition(".")
        assert separator and domain and verb, f"{permission.value!r} is not domain.verb"


def test_a_role_set_cannot_be_mutated_by_a_caller() -> None:
    """A caller that could add to a role's set would be redefining the role."""
    with pytest.raises(AttributeError):
        permissions_for(Role.VIEWER).add(Permission.ORG_DELETE)  # type: ignore[attr-defined]
