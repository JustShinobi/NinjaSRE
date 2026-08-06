"""The permission catalogue, and the five roles assembled from it.

A permission is atomic and reads ``domain.verb``. It never names a route, a
table, or a screen: those change, and a permission that moved with them would
make an operator's grant mean something different after a refactor.

**The roles nest.** ``viewer`` ⊂ ``responder`` ⊂ ``operator`` ⊂ ``admin`` ⊂
``owner``, strictly, and a test asserts it. Two overlapping-but-incomparable
roles is one more mental model than anybody holds at three in the morning, and
it turns every denial into a matrix lookup. Nesting means a denial always has
the same answer — "you need the next role up" — and that answer is one an
operator can act on without reading this file.

The cost of nesting is real and accepted: a support engineer who should read
configuration but never approve remediation does not have a role of their own.
They get ``responder`` at the nodes where that is true, which is what node
scoping is for (see ``authorisation``).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class Permission(StrEnum):
    """One atomic thing a principal may do, checked at the API boundary.

    ``is_read_only`` is derived from the verb rather than from a second list.
    A list would be a place for the two to disagree, and the disagreement would
    be invisible: a write permission mistakenly classified as a read is a
    ``viewer`` who can change things.
    """

    # Investigations and their output.
    INVESTIGATION_READ = "investigation.read"
    INVESTIGATION_RUN = "investigation.run"
    REPORT_READ = "report.read"

    # Learned material.
    MEMORY_READ = "memory.read"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"

    # Remediation, and the approvals in front of it.
    REMEDIATION_APPROVE = "remediation.approve"
    REMEDIATION_EXECUTE = "remediation.execute"
    APPROVAL_READ = "approval.read"
    APPROVAL_REVIEW = "approval.review"

    # Configuration and the integrations it points at.
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"
    INTEGRATION_MANAGE = "integration.manage"
    SCHEDULE_MANAGE = "schedule.manage"

    # Credentials. Reading metadata is not reading a value — there is no
    # permission that reveals one, because no code path does.
    CREDENTIAL_READ = "credential.read"
    CREDENTIAL_WRITE = "credential.write"

    # Who is who.
    IDENTITY_READ = "identity.read"
    IDENTITY_WRITE = "identity.write"
    TOKEN_MANAGE = "token.manage"
    SSO_MANAGE = "sso.manage"
    IMPERSONATION_USE = "impersonation.use"

    # The record, and the organisation itself.
    AUDIT_READ = "audit.read"
    AUDIT_EXPORT = "audit.export"
    ORG_MANAGE = "org.manage"
    ORG_DELETE = "org.delete"
    OWNER_ASSIGN = "owner.assign"

    @property
    def verb(self) -> str:
        """Return the part after the dot: ``read``, ``write``, ``manage``…"""
        return self.value.partition(".")[2]

    @property
    def domain(self) -> str:
        """Return the part before the dot, which is what an audit query groups by."""
        return self.value.partition(".")[0]

    @property
    def is_read_only(self) -> bool:
        """Return whether holding this permission can change nothing."""
        return self.verb in _READ_VERBS


#: Verbs that observe. Anything else is assumed to change something, so a verb
#: added without being listed here is treated as a write. Absence is never
#: permission.
_READ_VERBS: Final[frozenset[str]] = frozenset({"read"})


class Role(StrEnum):
    """A named permission set, granted to a principal at a node."""

    VIEWER = "viewer"
    RESPONDER = "responder"
    OPERATOR = "operator"
    ADMIN = "admin"
    OWNER = "owner"


#: Least to most privileged. The order is load-bearing: it is what "the next
#: role up" means in a denial message, and what the nesting test walks.
ROLE_ORDER: Final[tuple[Role, ...]] = (
    Role.VIEWER,
    Role.RESPONDER,
    Role.OPERATOR,
    Role.ADMIN,
    Role.OWNER,
)

#: What each role adds to the one below it. Written as increments rather than as
#: five complete sets, so a permission cannot be added to ``operator`` and
#: forgotten in ``admin`` — the nesting is a property of the construction.
_ROLE_INCREMENTS: Final[Mapping[Role, frozenset[Permission]]] = {
    Role.VIEWER: frozenset(
        {
            Permission.INVESTIGATION_READ,
            Permission.REPORT_READ,
            Permission.MEMORY_READ,
            Permission.KNOWLEDGE_READ,
            Permission.CONFIG_READ,
            Permission.APPROVAL_READ,
        }
    ),
    Role.RESPONDER: frozenset(
        {
            Permission.INVESTIGATION_RUN,
            Permission.REMEDIATION_APPROVE,
            Permission.REMEDIATION_EXECUTE,
            Permission.APPROVAL_REVIEW,
            Permission.KNOWLEDGE_WRITE,
        }
    ),
    Role.OPERATOR: frozenset(
        {
            Permission.CONFIG_WRITE,
            Permission.CREDENTIAL_READ,
            Permission.CREDENTIAL_WRITE,
            Permission.INTEGRATION_MANAGE,
            Permission.SCHEDULE_MANAGE,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.IDENTITY_READ,
            Permission.IDENTITY_WRITE,
            Permission.TOKEN_MANAGE,
            Permission.SSO_MANAGE,
            Permission.IMPERSONATION_USE,
            Permission.AUDIT_READ,
            Permission.AUDIT_EXPORT,
            Permission.ORG_MANAGE,
        }
    ),
    #: What separates an owner from an admin, and the whole of it: ending the
    #: organisation, and deciding who else may.
    Role.OWNER: frozenset({Permission.ORG_DELETE, Permission.OWNER_ASSIGN}),
}


def _accumulate() -> Mapping[Role, frozenset[Permission]]:
    """Return each role's full set, built by accumulating the increments."""
    resolved: dict[Role, frozenset[Permission]] = {}
    running: frozenset[Permission] = frozenset()
    for role in ROLE_ORDER:
        running = running | _ROLE_INCREMENTS[role]
        resolved[role] = running
    return resolved


#: The catalogue as callers read it: role to everything that role may do.
ROLE_PERMISSIONS: Final[Mapping[Role, frozenset[Permission]]] = _accumulate()


def permissions_for(role: Role) -> frozenset[Permission]:
    """Return everything ``role`` may do, its inherited permissions included."""
    return ROLE_PERMISSIONS[role]


def roles_granting(permission: Permission) -> tuple[Role, ...]:
    """Return the roles that hold ``permission``, least privileged first.

    What a denial message uses to say what to ask for: naming the *cheapest*
    role that would have worked is the difference between a request an admin
    approves and a request for ``owner`` that they refuse.
    """
    return tuple(role for role in ROLE_ORDER if permission in ROLE_PERMISSIONS[role])


__all__ = [
    "ROLE_ORDER",
    "ROLE_PERMISSIONS",
    "Permission",
    "Role",
    "permissions_for",
    "roles_granting",
]
