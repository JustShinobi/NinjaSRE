"""SC-004: a viewer sees no write control anywhere, asserted page by page, role by role.

The matrix is not a list of cases somebody wrote down. It is the product of two
things read from elsewhere — every role in ``platform/identity/permissions.py``
and every page in ``PAGES`` — so a role added to the catalogue or a page added to
the console is covered by having been added.

What is asserted is *absence*, not disabling. A disabled control would tell a
viewer that the deployment has a capability they lack, which is information
about the configuration and an invitation to escalate.
"""

from __future__ import annotations

import pytest

from platform.identity.permissions import ROLE_ORDER, Permission, Role, permissions_for
from surfaces.console.html import text_of
from surfaces.console.pages.shell import AREAS
from surfaces.console.permissions import (
    ACTION_PERMISSIONS,
    Action,
    Viewer,
    actions_in,
    write_actions_in,
)
from tests.unit.surfaces.console.conftest import PAGES, context_for, render, viewer_for


def test_every_declared_action_has_a_permission_nobody_forgot() -> None:
    assert set(ACTION_PERMISSIONS) == set(Action)


def test_a_viewer_holds_no_permission_that_writes() -> None:
    held = permissions_for(Role.VIEWER)

    assert all(permission.is_read_only for permission in held)


# --- SC-004 -------------------------------------------------------------------


def test_a_viewer_sees_no_write_control_on_any_page(page_name: str) -> None:
    document = render(page_name, Role.VIEWER)

    assert write_actions_in(document.body) == ()


def test_a_viewer_sees_no_declared_action_at_all_on_any_page(page_name: str) -> None:
    """Stronger than SC-004 and true today: every declared action needs a write.

    Asserted separately so that if an action is ever added that a viewer *may*
    perform, the failure lands here — where the question "should a viewer have
    this?" is being asked — rather than silently weakening the test above.
    """
    document = render(page_name, Role.VIEWER)

    assert actions_in(document.body) == ()


def test_every_page_renders_for_every_role_without_raising(page_name: str, role: Role) -> None:
    document = render(page_name, role)

    assert document.render().startswith("<!doctype html>")


def test_a_control_a_role_may_use_is_present_for_that_role(page_name: str) -> None:
    """The matrix would pass trivially if no page rendered a control at all."""
    owner_actions = set(actions_in(render(page_name, Role.OWNER).body))
    viewer_actions = set(actions_in(render(page_name, Role.VIEWER).body))

    assert viewer_actions <= owner_actions


def test_at_least_one_page_offers_each_declared_action_to_somebody() -> None:
    """A declared action nothing renders is a permission nobody can exercise here."""
    rendered: set[str] = set()
    for page_name in PAGES:
        rendered |= set(actions_in(render(page_name, Role.OWNER).body))

    unrendered = {str(action) for action in Action} - rendered
    assert unrendered == set(), f"declared but never rendered: {sorted(unrendered)}"


@pytest.mark.parametrize("role", ROLE_ORDER, ids=[role.value for role in ROLE_ORDER])
def test_a_role_never_sees_a_control_it_could_not_use(role: Role) -> None:
    held = permissions_for(role)

    for page_name in PAGES:
        for found in actions_in(render(page_name, role).body):
            action = Action(found)
            assert ACTION_PERMISSIONS[action] in held, (
                f"{page_name} offered {found} to {role.value}, who does not hold "
                f"{ACTION_PERMISSIONS[action].value}"
            )


def test_actions_escalate_with_the_role_because_the_roles_nest() -> None:
    seen: list[set[str]] = []
    for role in ROLE_ORDER:
        actions: set[str] = set()
        for page_name in PAGES:
            actions |= set(actions_in(render(page_name, role).body))
        seen.append(actions)

    for narrower, wider in zip(seen, seen[1:]):
        assert narrower <= wider


# --- Navigation is omitted too -------------------------------------------------


def test_a_viewer_is_not_offered_an_area_whose_data_it_cannot_read() -> None:
    context = context_for(Role.VIEWER)
    offered = {area.path for area in context.areas()}

    assert "/admin" not in offered
    assert "/onboarding" not in offered
    assert "/runs" in offered


def test_an_owner_is_offered_every_area() -> None:
    context = context_for(Role.OWNER)

    assert {area.path for area in context.areas()} == {area.path for area in AREAS}


def test_a_principal_holding_nothing_is_offered_no_area_at_all() -> None:
    from surfaces.console.pages.shell import PageContext

    assert PageContext(viewer=Viewer()).areas() == ()


# --- Impersonation (FR-024) -----------------------------------------------------


def test_an_impersonating_session_is_marked_on_every_page(page_name: str) -> None:
    document = render(page_name, Role.ADMIN, impersonating=True)

    banners = [node for node in document.body.walk() if node.has("data-impersonation")]
    if page_name == "sign-in":
        # A signed-out page has no session to be impersonating.
        assert banners == []
        return
    assert len(banners) == 1
    assert "acting as" in text_of(banners[0])


def test_a_page_that_is_not_impersonating_carries_no_banner(page_name: str) -> None:
    document = render(page_name, Role.ADMIN)

    assert [node for node in document.body.walk() if node.has("data-impersonation")] == []


# --- The viewer model itself ---------------------------------------------------


def test_a_viewer_is_built_from_what_the_api_said_rather_than_from_a_role_name() -> None:
    viewer = Viewer.of_principal(
        {
            "principal_id": "ada",
            "permissions": ["investigation.read", "config.write"],
            "roles": ["operator"],
        }
    )

    assert viewer.holds(Permission.CONFIG_WRITE)
    assert not viewer.holds(Permission.TOKEN_MANAGE)


def test_a_permission_this_console_has_never_heard_of_is_kept_rather_than_dropped() -> None:
    viewer = Viewer.of_principal({"permissions": ["investigation.read", "future.thing"]})

    assert viewer.unrecognised == ("future.thing",)
    assert viewer.holds(Permission.INVESTIGATION_READ)


def test_the_viewer_fixture_agrees_with_the_platform_catalogue(role: Role) -> None:
    assert viewer_for(role).permissions == frozenset(permissions_for(role))
