"""No privileged route reaches business logic without a permission check.

A permission model is worth exactly as much as its weakest unguarded route, and
"we will remember to add the check" is not a mechanism. This suite is the
mechanism: the route table is the *only* place a guard can be obtained from, so
a handler that never declared a permission has nothing to depend on, and this
test fails the build if a declaration is missing, contradictory, or unreachable.

The table is deliberately the source of truth rather than a shadow copy of a
mounted router. A second list that has to be kept in step with the first is a
list that eventually is not, and the failure mode of *that* design is a route
believed to be guarded and silently open.
"""

from __future__ import annotations

import pytest

from gateway.http.security.dependencies import PermissionGuard, requires
from gateway.http.security.route_permissions import (
    ROUTE_TABLE,
    Route,
    RouteTable,
    UndeclaredRoute,
)
from platform.identity.permissions import Permission

pytestmark = pytest.mark.security


def test_every_declared_route_resolves_to_a_permission_or_says_why_not() -> None:
    """The enumeration itself: no route is silently unguarded."""
    for route in ROUTE_TABLE.routes:
        assert (route.permission is None) != (route.public_because is None), (
            f"{route.method} {route.path} must declare a permission or say why it is public"
        )


def test_a_public_route_gives_a_reason_a_reviewer_can_argue_with() -> None:
    """ "Public" is a decision somebody made, so it is recorded as prose."""
    for route in ROUTE_TABLE.public_routes():
        assert route.public_because is not None
        assert len(route.public_because) >= 16, (
            f"{route.method} {route.path} is public for a reason nobody can review"
        )


def test_every_declared_permission_is_in_the_catalogue() -> None:
    """A route cannot demand a permission no role can hold."""
    for route in ROUTE_TABLE.routes:
        if route.permission is not None:
            assert route.permission in set(Permission)


def test_the_table_declares_each_route_once() -> None:
    """Two declarations for one route is two answers to "may I"."""
    keys = [(route.method, route.path) for route in ROUTE_TABLE.routes]
    assert len(keys) == len(set(keys))


def test_a_route_cannot_be_both_guarded_and_public() -> None:
    """Constructing the contradiction fails, rather than resolving it silently."""
    with pytest.raises(ValueError):
        Route(
            method="POST",
            path="/config/{node_id}",
            permission=Permission.CONFIG_WRITE,
            public_because="it is also open to everybody",
        )


def test_a_route_that_declares_nothing_is_refused_at_construction() -> None:
    """The absent declaration fails where it is written, not where it is served."""
    with pytest.raises(ValueError):
        Route(method="POST", path="/config/{node_id}")


def test_an_undeclared_route_cannot_obtain_a_guard() -> None:
    """This is what makes the check unbypassable rather than merely conventional.

    A handler asks the table for its guard. A route nobody declared raises here,
    at wiring time, so the application does not start rather than starting with
    an open route.
    """
    with pytest.raises(UndeclaredRoute) as raised:
        ROUTE_TABLE.guard_for("POST", "/routes/nobody/declared")

    assert "/routes/nobody/declared" in str(raised.value)


def test_a_guarded_route_yields_a_guard_carrying_its_permission() -> None:
    """The guard a route hands out is the permission the table declared."""
    guarded = next(route for route in ROUTE_TABLE.routes if route.permission is not None)
    guard = ROUTE_TABLE.guard_for(guarded.method, guarded.path)
    assert isinstance(guard, PermissionGuard)
    assert guard.permission is guarded.permission


def test_a_public_route_yields_no_guard() -> None:
    """A public route is not guarded by a permission nobody could hold."""
    public = next(iter(ROUTE_TABLE.public_routes()), None)
    assert public is not None, "the table should declare at least the sign-in routes"
    assert ROUTE_TABLE.guard_for(public.method, public.path) is None


def test_the_table_refuses_a_duplicate_declaration() -> None:
    """Two rows for one route is caught when the table is built."""
    route = Route(method="GET", path="/x", permission=Permission.CONFIG_READ)
    with pytest.raises(ValueError):
        RouteTable.of((route, route))


def test_methods_and_paths_are_normalised_so_a_check_cannot_be_missed_by_spelling() -> None:
    """``get`` and ``GET`` are one route, and so are ``/x`` and ``/x/``.

    A guard that could be evaded by a trailing slash is not a guard.
    """
    table = RouteTable.of((Route(method="get", path="/x/", permission=Permission.CONFIG_READ),))
    assert table.guard_for("GET", "/x") is not None
    assert table.guard_for("get", "/x/") is not None


def test_requires_produces_a_guard_bound_to_one_permission() -> None:
    """``requires`` is the only way to build a guard, and it names its permission."""
    guard = requires(Permission.AUDIT_EXPORT)
    assert guard.permission is Permission.AUDIT_EXPORT


def test_every_privileged_route_kind_is_represented() -> None:
    """The table covers the surfaces this feature introduces.

    Later features add rows. This assertion is here so that "the table is empty
    and therefore trivially complete" is never how the suite passes.
    """
    paths = {route.path for route in ROUTE_TABLE.routes}
    assert any("token" in path for path in paths)
    assert any("audit" in path for path in paths)
    assert any("impersonation" in path for path in paths)
