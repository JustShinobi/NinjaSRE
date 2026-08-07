"""Who may ask NinjaSRE something, and what they may ask.

Three checks, in this order, and the order is the specification.

1. **A token, or nothing.** There is no anonymous mode and no flag that adds
   one. A surface reachable without a credential is a surface that answers
   whoever finds it.
2. **The permission for the operation.** Each exposed operation names one
   permission from the same table the REST API is checked against — not a
   parallel list, because a parallel list is where the two eventually disagree
   and the disagreement is a privilege.
3. **The team.** A token scoped to a team may address that team and nothing
   else. Checked explicitly rather than inferred, because a permission check
   proves the caller may act *somewhere*, not that the requested team is where.

Every refusal carries a reason for the audit trail and none of them carries it
to the caller, who is told the same sentence whatever went wrong. Telling
somebody their token was recognised but under-permissioned tells them the token
was recognised.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from platform.identity.authorisation import PermissionSet
from platform.identity.permissions import Permission
from platform.persistence.ports import TenantScope

#: One sentence, for every refusal, whatever caused it.
ACCESS_REFUSED_MESSAGE: Final = (
    "this request was refused. NinjaSRE's protocol surface requires a token with the "
    "permission for the operation, scoped to the team being addressed."
)


class AccessRefused(Exception):
    """A caller may not do this. ``reason`` is for the audit trail, never the caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(ACCESS_REFUSED_MESSAGE)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SurfaceCaller:
    """An authenticated external client, reduced to what authorisation reads."""

    principal_id: str
    org_id: str
    team_id: str
    permissions: PermissionSet

    @property
    def scope(self) -> TenantScope:
        """Return the tenant scope every read this caller makes is opened in."""
        return TenantScope(org_id=self.org_id, team_node_id=self.team_id or None)

    def holds(self, permission: Permission) -> bool:
        """Return whether this caller may perform ``permission`` at its own team."""
        return self.permissions.allows(permission, node_id=self.team_id or None)


@runtime_checkable
class TokenAuthenticator(Protocol):
    """Resolves a bearer secret to a principal and what it may do.

    Structurally satisfied by ``platform.identity.tokens.TokenService``: the
    surface takes a port rather than the service so that this package stays
    testable without a database, and so a deployment that authenticates machine
    clients some other way substitutes one class.
    """

    async def authenticate(self, secret: str) -> object:
        """Return the authenticated token, or raise for anything that is not one."""


def caller_of(authenticated: object) -> SurfaceCaller:
    """Return the caller an ``AuthenticatedToken`` describes.

    Reads the three attributes the identity layer guarantees rather than
    importing its type, so the surface keeps working if the token record grows
    a field and keeps refusing if it loses one.
    """
    principal = getattr(authenticated, "principal", None)
    permissions = getattr(authenticated, "permissions", None)
    scope = getattr(authenticated, "scope", None)
    if principal is None or not isinstance(permissions, PermissionSet) or scope is None:
        raise AccessRefused("the authenticator returned something that is not a resolved token")
    return SurfaceCaller(
        principal_id=str(getattr(principal, "id", "") or getattr(principal, "principal_id", "")),
        org_id=str(getattr(scope, "org_id", "")),
        team_id=str(getattr(scope, "team_node_id", "") or ""),
        permissions=permissions,
    )


async def authenticate(authenticator: TokenAuthenticator, secret: str) -> SurfaceCaller:
    """Return who ``secret`` is, or raise ``AccessRefused``."""
    if not secret.strip():
        raise AccessRefused("no token was presented")
    try:
        resolved = await authenticator.authenticate(secret)
    except AccessRefused:
        raise
    except Exception as error:  # noqa: BLE001 — every rejection is one refusal
        raise AccessRefused(f"the token was not accepted: {type(error).__name__}") from error
    return caller_of(resolved)


def authorise(
    caller: SurfaceCaller,
    *,
    operation: str,
    permission: Permission,
    team_id: str = "",
) -> None:
    """Raise ``AccessRefused`` unless ``caller`` may perform ``operation``."""
    if not caller.holds(permission):
        raise AccessRefused(
            f"{caller.principal_id or 'the caller'} does not hold {permission.value} "
            f"for {operation}"
        )
    if team_id and caller.team_id and team_id != caller.team_id:
        raise AccessRefused(
            f"{caller.principal_id or 'the caller'} is scoped to {caller.team_id!r} and "
            f"addressed {team_id!r}"
        )


def audit_detail(
    caller: SurfaceCaller, *, operation: str, arguments: Mapping[str, object]
) -> dict[str, object]:
    """Return the audit payload for one external invocation.

    Argument *names* only. What an external agent asked about may name an
    incident, a customer, or a service nobody outside the team should be able to
    enumerate from the audit table, and the operation plus the caller is what a
    review of this surface actually needs.
    """
    return {
        "operation": operation,
        "team_id": caller.team_id,
        "arguments": sorted(str(name) for name in arguments),
    }


__all__ = [
    "ACCESS_REFUSED_MESSAGE",
    "AccessRefused",
    "SurfaceCaller",
    "TokenAuthenticator",
    "audit_detail",
    "authenticate",
    "authorise",
    "caller_of",
]
