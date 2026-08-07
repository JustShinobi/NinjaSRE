"""Rendering by what a principal holds, by omitting rather than by disabling.

A disabled control tells a user two things they were not entitled to learn: that
the capability exists in this deployment, and that somebody else has it. The
first is information about how the deployment is configured; the second is an
invitation to go and ask for it. Absence leaks neither, and it also removes the
entire class of "why can't I click this".

So there is no ``disabled`` path here. ``if_permitted`` returns ``None`` when
the permission is not held, and ``html.element`` drops a ``None`` child — which
means a permission-gated control is an expression rather than a branch, and a
caller cannot half-implement the rule by rendering the control and forgetting
the guard.

**This is not the security boundary.** The API checks every request against the
same permission catalogue (``platform/identity/permissions.py``) and refuses
regardless of what was rendered. What this buys is that the console does not
show somebody a button that will fail, and that a test can prove it: every
control that changes something carries ``data-action``, so the role matrix walks
a page and asserts that a viewer's page contains no such attribute at all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from platform.identity.permissions import Permission
from surfaces.console.html import Element

#: The attribute every state-changing control carries. One name, so the role
#: matrix has one thing to look for and a control that forgot it is a control
#: the matrix would not have checked — which is why ``action_control`` is the
#: only way to build one.
ACTION_ATTRIBUTE: Final = "data-action"


class Action(StrEnum):
    """Something a user can do that changes state, and what it needs.

    Named for what the user is doing rather than for the route it calls: a route
    is an implementation detail that moves, and a grant an operator makes has to
    keep meaning the same thing afterwards.
    """

    START_INVESTIGATION = "investigation.start"
    CANCEL_INVESTIGATION = "investigation.cancel"
    ADD_CONTEXT = "investigation.add_context"
    TAKE_OVER = "investigation.take_over"
    ANSWER_QUESTION = "interaction.answer"
    APPROVE_CHANGE = "approval.approve"
    REJECT_CHANGE = "approval.reject"
    ROLLBACK = "remediation.rollback"
    EDIT_STRATEGY = "strategy.edit"
    REVIEW_PROPOSAL = "knowledge.review_proposal"
    EDIT_CONFIG = "config.edit"
    APPLY_TEMPLATE = "config.apply_template"
    CONNECT_INTEGRATION = "integration.connect"
    MANAGE_SCHEDULE = "schedule.manage"
    CREATE_TOKEN = "token.create"
    REVOKE_TOKEN = "token.revoke"
    EDIT_GRANT = "identity.edit_grant"
    EDIT_POLICY = "policy.edit"
    CONFIGURE_SSO = "sso.configure"
    EXPORT_AUDIT = "audit.export"
    IMPERSONATE = "impersonation.begin"


#: What each action requires. Every action has a row: an action missing from
#: this table cannot be rendered at all, because ``action_control`` looks its
#: permission up here and raises when there is none. A control nobody decided
#: the permission for is not a control that should reach a page.
ACTION_PERMISSIONS: Final[Mapping[Action, Permission]] = {
    Action.START_INVESTIGATION: Permission.INVESTIGATION_RUN,
    Action.CANCEL_INVESTIGATION: Permission.INVESTIGATION_RUN,
    Action.ADD_CONTEXT: Permission.INVESTIGATION_RUN,
    Action.TAKE_OVER: Permission.INVESTIGATION_RUN,
    Action.ANSWER_QUESTION: Permission.INVESTIGATION_RUN,
    Action.APPROVE_CHANGE: Permission.REMEDIATION_APPROVE,
    Action.REJECT_CHANGE: Permission.REMEDIATION_APPROVE,
    Action.ROLLBACK: Permission.REMEDIATION_EXECUTE,
    Action.EDIT_STRATEGY: Permission.KNOWLEDGE_WRITE,
    Action.REVIEW_PROPOSAL: Permission.KNOWLEDGE_WRITE,
    Action.EDIT_CONFIG: Permission.CONFIG_WRITE,
    Action.APPLY_TEMPLATE: Permission.CONFIG_WRITE,
    Action.CONNECT_INTEGRATION: Permission.CREDENTIAL_WRITE,
    Action.MANAGE_SCHEDULE: Permission.SCHEDULE_MANAGE,
    Action.CREATE_TOKEN: Permission.TOKEN_MANAGE,
    Action.REVOKE_TOKEN: Permission.TOKEN_MANAGE,
    Action.EDIT_GRANT: Permission.IDENTITY_WRITE,
    Action.EDIT_POLICY: Permission.ORG_MANAGE,
    Action.CONFIGURE_SSO: Permission.SSO_MANAGE,
    Action.EXPORT_AUDIT: Permission.AUDIT_EXPORT,
    Action.IMPERSONATE: Permission.IMPERSONATION_USE,
}


class UndeclaredAction(LookupError):
    """A control was built for an action nobody declared a permission for.

    Raised where the control is written rather than where it is served, which is
    the same bargain ``gateway/http/security/route_permissions.py`` makes: a
    thing with no declared permission must not be constructible.
    """

    def __init__(self, action: str) -> None:
        super().__init__(
            f"{action!r} has no row in ACTION_PERMISSIONS. A control that changes something "
            f"needs a declared permission, or the role matrix has nothing to check it against."
        )
        self.action = action


@dataclass(frozen=True, slots=True)
class Viewer:
    """Who is looking at the page, and what they may do at their own node.

    Built from what ``GET /auth/me`` answered and nothing else. The console
    never derives a permission from a role name of its own — that would be a
    second copy of the catalogue, and the copy would be the one that was wrong
    after somebody added a permission.
    """

    principal_id: str = ""
    display_name: str = ""
    team_node_id: str = ""
    permissions: frozenset[Permission] = frozenset()
    roles: tuple[str, ...] = ()
    #: Whether this session is somebody acting as somebody else. Rendered as a
    #: banner on every page, because an admin who forgets they are impersonating
    #: is an admin about to attribute their own action to a colleague.
    impersonating: bool = False
    impersonated_by: str | None = None
    #: Unknown permission strings the API returned. Kept rather than discarded so
    #: a console running against a newer deployment can say so instead of
    #: silently treating a permission it has never heard of as absent.
    unrecognised: tuple[str, ...] = ()

    @classmethod
    def of_principal(cls, payload: Mapping[str, Any]) -> Viewer:
        """Return the viewer ``GET /auth/me`` described."""
        held: set[Permission] = set()
        unknown: list[str] = []
        for name in payload.get("permissions") or ():
            try:
                held.add(Permission(name))
            except ValueError:
                unknown.append(str(name))
        return cls(
            principal_id=str(payload.get("principal_id", "")),
            display_name=str(payload.get("display_name", "")),
            team_node_id=str(payload.get("team_node_id", "")),
            permissions=frozenset(held),
            roles=tuple(str(role) for role in payload.get("roles") or ()),
            impersonating=bool(payload.get("impersonating", False)),
            impersonated_by=payload.get("impersonated_by"),
            unrecognised=tuple(sorted(unknown)),
        )

    def holds(self, permission: Permission) -> bool:
        """Return whether this viewer holds ``permission`` at their own node."""
        return permission in self.permissions

    def may(self, action: Action) -> bool:
        """Return whether this viewer may perform ``action``."""
        required = ACTION_PERMISSIONS.get(action)
        if required is None:
            raise UndeclaredAction(str(action))
        return required in self.permissions

    @property
    def is_read_only(self) -> bool:
        """Return whether nothing this viewer holds can change anything."""
        return all(permission.is_read_only for permission in self.permissions)

    def permitted_actions(self) -> tuple[Action, ...]:
        """Return every action this viewer may perform, in declaration order."""
        return tuple(action for action in Action if self.may(action))


@dataclass(frozen=True, slots=True)
class ReadOnly:
    """A viewer holding nothing, for a page rendered before anybody signed in."""

    viewer: Viewer = field(default_factory=Viewer)


def if_permitted(
    viewer: Viewer, permission: Permission, build: Callable[[], Element]
) -> Element | None:
    """Return what ``build`` produces, or ``None`` when ``permission`` is not held.

    ``build`` is a callable rather than a value so the element is never
    constructed for somebody who will not see it — which matters when building
    it would mean formatting data the viewer is not entitled to.
    """
    return build() if viewer.holds(permission) else None


def if_may(viewer: Viewer, action: Action, build: Callable[[], Element]) -> Element | None:
    """Return what ``build`` produces, or ``None`` when ``action`` is not permitted."""
    return build() if viewer.may(action) else None


def action_control(viewer: Viewer, action: Action, build: Callable[[], Element]) -> Element | None:
    """Return a state-changing control, tagged with its action, or ``None``.

    The only sanctioned way to render something that changes state. It does two
    things a caller must not do separately: it omits the control when the action
    is not permitted, and it stamps ``data-action`` on what it returns so the
    role matrix can find it. A control built without this is a control the
    matrix cannot see, which is the failure mode the attribute exists to
    prevent.
    """
    if not viewer.may(action):
        return None
    built = build()
    return Element(
        tag=built.tag,
        attributes={**built.attributes, ACTION_ATTRIBUTE: str(action)},
        children=built.children,
    )


def actions_in(root: Element) -> tuple[str, ...]:
    """Return every declared action present in a rendered tree, in document order.

    What the role matrix asserts on. An empty answer for a read-only role is the
    property SC-004 states, and it is checkable on any page without that page
    knowing it is being checked.
    """
    return tuple(
        str(node.attribute(ACTION_ATTRIBUTE)) for node in root.walk() if node.has(ACTION_ATTRIBUTE)
    )


def write_actions_in(root: Element) -> tuple[str, ...]:
    """Return the actions in ``root`` that require a permission which writes."""
    declared = {str(action): ACTION_PERMISSIONS[action] for action in Action}
    return tuple(
        found
        for found in actions_in(root)
        if found in declared and not declared[found].is_read_only
    )


def permissions_of(names: Iterable[str]) -> frozenset[Permission]:
    """Return the permissions ``names`` spells, ignoring anything unrecognised."""
    found: set[Permission] = set()
    for name in names:
        try:
            found.add(Permission(name))
        except ValueError:
            continue
    return frozenset(found)


__all__ = [
    "ACTION_ATTRIBUTE",
    "ACTION_PERMISSIONS",
    "Action",
    "ReadOnly",
    "UndeclaredAction",
    "Viewer",
    "action_control",
    "actions_in",
    "if_may",
    "if_permitted",
    "permissions_of",
    "write_actions_in",
]
