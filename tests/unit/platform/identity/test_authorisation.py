"""Node-scoped permission resolution, and the one removal the system refuses.

Two behaviours, and both are the kind that is cheap to get subtly wrong. A grant
inherits *downward* and never upward, so an operator granted at a team cannot
reach the organisation that contains it. And an organisation may never be left
without an owner, however the last one is removed.
"""

from __future__ import annotations

import pytest

from platform.config_service.hierarchy import Hierarchy
from platform.identity.authorisation import PermissionSet, owners_in, require_owner_retained
from platform.identity.errors import LastOwnerRemoval, PermissionDenied
from platform.identity.models import Grant
from platform.identity.permissions import Permission, Role
from platform.persistence.ports import ConfigNode, ConfigNodeKind

ORG = "acme"
PLATFORM = "platform"
PAYMENTS = "payments"
CHECKOUT = "checkout"


def hierarchy() -> Hierarchy:
    """Return acme → {platform, payments → checkout}."""
    return Hierarchy.of(
        (
            ConfigNode(node_id=ORG, name="Acme", kind=ConfigNodeKind.ORGANISATION, parent_id=None),
            ConfigNode(node_id=PLATFORM, name="Platform", kind=ConfigNodeKind.TEAM, parent_id=ORG),
            ConfigNode(node_id=PAYMENTS, name="Payments", kind=ConfigNodeKind.TEAM, parent_id=ORG),
            ConfigNode(
                node_id=CHECKOUT,
                name="Checkout",
                kind=ConfigNodeKind.SERVICE,
                parent_id=PAYMENTS,
            ),
        )
    )


def grant(role: Role, node_id: str | None, *, principal: str = "erin") -> Grant:
    """Return one role granted to ``principal`` at ``node_id``."""
    return Grant(
        grant_id=f"{principal}-{role.value}-{node_id or 'org'}",
        principal_id=principal,
        role=role,
        node_id=node_id,
    )


def test_a_grant_applies_at_the_node_it_was_made_at() -> None:
    """The unsurprising half, asserted so the surprising half has a baseline."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, PAYMENTS),), hierarchy=hierarchy())
    assert held.allows(Permission.CONFIG_WRITE, node_id=PAYMENTS)


def test_a_grant_reaches_every_descendant() -> None:
    """A grant at a team covers the services beneath it."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, PAYMENTS),), hierarchy=hierarchy())
    assert held.allows(Permission.CONFIG_WRITE, node_id=CHECKOUT)


def test_a_grant_never_reaches_upward_or_sideways() -> None:
    """Inheritance is downward only, which is the half that is a security bound."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, PAYMENTS),), hierarchy=hierarchy())
    assert not held.allows(Permission.CONFIG_WRITE, node_id=ORG)
    assert not held.allows(Permission.CONFIG_WRITE, node_id=PLATFORM)


def test_an_organisation_wide_grant_covers_every_node() -> None:
    """A grant with no node is the whole tenant, root included."""
    held = PermissionSet(grants=(grant(Role.ADMIN, None),), hierarchy=hierarchy())
    for node in (ORG, PLATFORM, PAYMENTS, CHECKOUT, None):
        assert held.allows(Permission.CONFIG_WRITE, node_id=node)


def test_two_grants_at_different_nodes_are_the_union_where_they_overlap() -> None:
    """A viewer everywhere and an operator on one team is both, on that team."""
    held = PermissionSet(
        grants=(grant(Role.VIEWER, None), grant(Role.OPERATOR, PAYMENTS)),
        hierarchy=hierarchy(),
    )
    assert held.allows(Permission.CONFIG_READ, node_id=PLATFORM)
    assert not held.allows(Permission.CONFIG_WRITE, node_id=PLATFORM)
    assert held.allows(Permission.CONFIG_WRITE, node_id=CHECKOUT)


def test_an_unknown_node_is_refused_rather_than_treated_as_the_root() -> None:
    """Resolving against a node that is not in the tree denies.

    Falling back to the root would turn a typo in a path parameter into an
    organisation-wide check, which is the wrong direction for a mistake to fail.
    """
    held = PermissionSet(grants=(grant(Role.OWNER, None),), hierarchy=hierarchy())
    assert not held.allows(Permission.CONFIG_WRITE, node_id="not-a-node")


def test_a_denial_names_the_permission_and_the_scope() -> None:
    """The message says what to ask for, not merely that you may not."""
    held = PermissionSet(grants=(grant(Role.VIEWER, None),), hierarchy=hierarchy())
    with pytest.raises(PermissionDenied) as raised:
        held.require(Permission.CONFIG_WRITE, node_id=PAYMENTS)

    message = str(raised.value)
    assert Permission.CONFIG_WRITE.value in message
    assert PAYMENTS in message
    assert raised.value.permission is Permission.CONFIG_WRITE
    assert raised.value.node_id == PAYMENTS


def test_resolution_works_without_a_hierarchy() -> None:
    """A deployment that has not loaded its tree still resolves exact grants.

    Without ancestry there is no inheritance to apply, so a node grant covers
    that node alone. Denying more than it should is the safe direction.
    """
    held = PermissionSet(grants=(grant(Role.OPERATOR, PAYMENTS),))
    assert held.allows(Permission.CONFIG_WRITE, node_id=PAYMENTS)
    assert not held.allows(Permission.CONFIG_WRITE, node_id=CHECKOUT)


# --- Last owner protection ------------------------------------------


def test_owners_are_those_holding_owner_at_the_organisation() -> None:
    """An owner is an owner of the tenant; there is no owner of one team."""
    grants = (
        grant(Role.OWNER, None, principal="ada"),
        grant(Role.OWNER, PAYMENTS, principal="grace"),
        grant(Role.ADMIN, None, principal="erin"),
    )
    assert owners_in(grants) == frozenset({"ada"})


def test_removing_one_of_two_owners_is_allowed() -> None:
    """The protection is about the last one, not about owners in general."""
    grants = (grant(Role.OWNER, None, principal="ada"), grant(Role.OWNER, None, principal="grace"))
    require_owner_retained(grants, removing=(grants[0].grant_id,))


def test_removing_the_last_owner_is_refused() -> None:
    """An organisation can never be left without an owner."""
    grants = (grant(Role.OWNER, None, principal="ada"), grant(Role.ADMIN, None, principal="erin"))
    with pytest.raises(LastOwnerRemoval) as raised:
        require_owner_retained(grants, removing=(grants[0].grant_id,))

    assert "ada" in str(raised.value)


def test_removing_every_owner_at_once_is_refused() -> None:
    """Bulk removal is the path a per-removal check misses."""
    grants = (grant(Role.OWNER, None, principal="ada"), grant(Role.OWNER, None, principal="grace"))
    with pytest.raises(LastOwnerRemoval):
        require_owner_retained(grants, removing=(grants[0].grant_id, grants[1].grant_id))


def test_an_owner_demoting_themselves_is_refused_when_they_are_the_last() -> None:
    """The edge case the specification names: the last admin removing their own role."""
    grants = (grant(Role.OWNER, None, principal="ada"),)
    with pytest.raises(LastOwnerRemoval):
        require_owner_retained(grants, removing=(grants[0].grant_id,))


def test_replacing_the_last_owner_in_one_step_is_allowed() -> None:
    """Handing over ownership must not require a moment with no owner."""
    grants = (grant(Role.OWNER, None, principal="ada"),)
    require_owner_retained(
        grants,
        removing=(grants[0].grant_id,),
        adding=(grant(Role.OWNER, None, principal="grace"),),
    )


# --- Narrowing (what a scoped credential gets) -------------------------------


def test_a_narrowed_set_holds_no_more_than_the_principal_does() -> None:
    """A token can be less than its owner and never more."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, None),), hierarchy=hierarchy())
    scoped = held.narrowed_to((Permission.CONFIG_READ, Permission.ORG_DELETE))

    assert scoped.allows(Permission.CONFIG_READ, node_id=PAYMENTS)
    assert not scoped.allows(Permission.ORG_DELETE, node_id=PAYMENTS)
    assert not scoped.allows(Permission.CONFIG_WRITE, node_id=PAYMENTS)


def test_narrowing_twice_cannot_widen_the_first_narrowing() -> None:
    """A narrowing that can widen is not one."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, None),), hierarchy=hierarchy())
    once = held.narrowed_to((Permission.CONFIG_READ,))
    twice = once.narrowed_to((Permission.CONFIG_WRITE, Permission.CONFIG_READ))

    assert not twice.allows(Permission.CONFIG_WRITE, node_id=PAYMENTS)
    assert twice.allows(Permission.CONFIG_READ, node_id=PAYMENTS)


def test_a_narrowed_set_still_obeys_node_scoping() -> None:
    """Narrowing caps what is held; it does not change where it is held."""
    held = PermissionSet(grants=(grant(Role.OPERATOR, PAYMENTS),), hierarchy=hierarchy())
    scoped = held.narrowed_to((Permission.CONFIG_WRITE,))

    assert scoped.allows(Permission.CONFIG_WRITE, node_id=CHECKOUT)
    assert not scoped.allows(Permission.CONFIG_WRITE, node_id=PLATFORM)
