"""The guard a route depends on: what it lets through, and what it says when it does not.

The check is a value over a request context rather than anything framework-shaped,
so these tests need no server. That is the property being asserted as much as any
individual case: a permission decision that required a running transport to
exercise would be one nobody exercised.
"""

from __future__ import annotations

import pytest

from gateway.http.security.dependencies import PermissionGuard, RequestContext, requires
from platform.config_service.hierarchy import Hierarchy
from platform.identity.authorisation import PermissionSet
from platform.identity.errors import PermissionDenied
from platform.identity.models import Grant, Principal
from platform.identity.permissions import Permission, Role
from platform.persistence.ports import ConfigNode, ConfigNodeKind, PrincipalKind

ORG = "acme"
PAYMENTS = "payments"
PLATFORM = "platform"
CHECKOUT = "checkout"


def hierarchy() -> Hierarchy:
    """Return acme → {platform, payments → checkout}."""
    return Hierarchy.of(
        (
            ConfigNode(node_id=ORG, name="Acme", kind=ConfigNodeKind.ORGANISATION, parent_id=None),
            ConfigNode(node_id=PLATFORM, name="Platform", kind=ConfigNodeKind.TEAM, parent_id=ORG),
            ConfigNode(node_id=PAYMENTS, name="Payments", kind=ConfigNodeKind.TEAM, parent_id=ORG),
            ConfigNode(
                node_id=CHECKOUT, name="Checkout", kind=ConfigNodeKind.SERVICE, parent_id=PAYMENTS
            ),
        )
    )


def held(role: Role, node_id: str | None = None, *, who: str = "ada") -> PermissionSet:
    """Return ``who``'s permissions from a single grant."""
    return PermissionSet(
        grants=(Grant(grant_id="g1", principal_id=who, role=role, node_id=node_id),),
        hierarchy=hierarchy(),
    )


def human(*, active: bool = True) -> Principal:
    """Return a signed-in human."""
    return Principal(principal_id="ada", org_id=ORG, display_name="Ada", is_active=active)


def machine(node_id: str | None) -> Principal:
    """Return a token principal scoped to ``node_id``."""
    return Principal(
        principal_id="ada",
        org_id=ORG,
        kind=PrincipalKind.SERVICE_ACCOUNT,
        display_name="payments bot",
        token_id="tok-1",
        node_id=node_id,
    )


def test_a_holder_passes() -> None:
    """The baseline the refusals below are measured against."""
    guard = requires(Permission.CONFIG_WRITE)
    context = RequestContext(
        principal=human(), permissions=held(Role.OPERATOR, PAYMENTS), node_id=PAYMENTS
    )
    assert guard(context).principal_id == "ada"


def test_somebody_without_the_permission_is_refused() -> None:
    """The check is the whole reason the boundary exists."""
    guard = requires(Permission.CONFIG_WRITE)
    context = RequestContext(principal=human(), permissions=held(Role.VIEWER), node_id=PAYMENTS)
    with pytest.raises(PermissionDenied):
        guard(context)


def test_the_refusal_names_the_permission_the_scope_and_a_role_to_ask_for() -> None:
    """A denial somebody can act on, rather than a wall."""
    guard = requires(Permission.CONFIG_WRITE)
    context = RequestContext(principal=human(), permissions=held(Role.VIEWER), node_id=PAYMENTS)

    with pytest.raises(PermissionDenied) as raised:
        guard(context)

    message = str(raised.value)
    assert Permission.CONFIG_WRITE.value in message
    assert PAYMENTS in message
    assert Role.OPERATOR.value in message, "the cheapest sufficient role, not the highest"


def test_the_permission_is_resolved_against_the_node_the_request_names() -> None:
    """One guard, and the node makes it mean something different per request."""
    guard = requires(Permission.CONFIG_WRITE)
    permissions = held(Role.OPERATOR, PAYMENTS)

    assert guard.allows(
        RequestContext(principal=human(), permissions=permissions, node_id=CHECKOUT)
    )
    assert not guard.allows(
        RequestContext(principal=human(), permissions=permissions, node_id=PLATFORM)
    )


def test_a_deactivated_principal_is_refused_whatever_they_hold() -> None:
    """Deactivation has to bite before the permission lookup, not after."""
    guard = requires(Permission.CONFIG_READ)
    context = RequestContext(
        principal=human(active=False), permissions=held(Role.OWNER), node_id=PAYMENTS
    )
    with pytest.raises(PermissionDenied):
        guard(context)


def test_a_token_cannot_widen_its_scope_by_addressing_another_node() -> None:
    """Acceptance scenario 3: a team-scoped token acts only within that team.

    The token's own node wins over the one in the path, so asking about another
    team resolves where the token lives — and holds nothing there for the node
    that was asked about.
    """
    guard = requires(Permission.CONFIG_WRITE)
    context = RequestContext(
        principal=machine(PAYMENTS),
        permissions=held(Role.OPERATOR, PLATFORM),
        node_id=PLATFORM,
    )

    assert context.scope_node_id == PAYMENTS
    with pytest.raises(PermissionDenied):
        guard(context)


def test_an_unscoped_token_resolves_against_the_node_in_the_request() -> None:
    """A personal access token is as wide as its owner, and no wider."""
    guard = requires(Permission.CONFIG_WRITE)
    context = RequestContext(
        principal=machine(None), permissions=held(Role.OPERATOR, PAYMENTS), node_id=PAYMENTS
    )
    assert guard.allows(context)


def test_a_request_with_no_permissions_at_all_is_refused() -> None:
    """The default context holds nothing, so a forgotten assignment fails closed."""
    guard = requires(Permission.INVESTIGATION_READ)
    with pytest.raises(PermissionDenied):
        guard(RequestContext(principal=human()))


def test_a_guard_reports_which_permission_it_carries() -> None:
    """A route's requirement is readable without invoking it."""
    guard = requires(Permission.AUDIT_EXPORT)
    assert isinstance(guard, PermissionGuard)
    assert guard.permission is Permission.AUDIT_EXPORT


def test_allows_is_the_same_decision_as_calling_it() -> None:
    """Two ways to ask must not become two answers."""
    guard = requires(Permission.CONFIG_WRITE)
    permitted = RequestContext(
        principal=human(), permissions=held(Role.OPERATOR, PAYMENTS), node_id=PAYMENTS
    )
    refused = RequestContext(principal=human(), permissions=held(Role.VIEWER), node_id=PAYMENTS)

    assert guard.allows(permitted)
    assert guard(permitted) is permitted.principal
    assert not guard.allows(refused)
