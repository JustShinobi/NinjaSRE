"""Teams user to NinjaSRE principal, mapped by the identifier an operator has.

Teams gives a conversation-scoped user id (``29:…``) and, on a roster lookup, an
Azure AD object id and a user principal name. An operator setting this up has
the last of those and none of the first, so the mapping accepts either and the
resolution tries the Teams id first and the account second.

Trying the account *second* rather than first is deliberate: the Teams id is
unambiguous, and an account claim is only as trustworthy as the roster lookup
that produced it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from config.constants.surfaces import CHAT_PLATFORM_MICROSOFT_TEAMS
from gateway.chat.identity import ChatIdentity
from gateway.chat.port import PlatformUser
from platform.identity.permissions import Permission, Role, permissions_for


def teams_user(
    user_id: str, *, tenant_id: str, display_name: str = "", account: str = ""
) -> PlatformUser:
    """Return the platform user a Teams id in ``tenant_id`` names."""
    return PlatformUser(
        platform=CHAT_PLATFORM_MICROSOFT_TEAMS,
        user_id=user_id,
        display_name=display_name,
        workspace_id=tenant_id,
        email=account,
    )


def teams_identity(
    *,
    user_id: str,
    tenant_id: str,
    principal_id: str,
    node_id: str = "",
    display_name: str = "",
) -> ChatIdentity:
    """Return the mapping row for one Teams user."""
    return ChatIdentity(
        platform=CHAT_PLATFORM_MICROSOFT_TEAMS,
        platform_user_id=user_id,
        workspace_id=tenant_id,
        principal_id=principal_id,
        node_id=node_id,
        display_name=display_name,
    )


@dataclass(frozen=True, slots=True)
class TeamsIdentityDirectory:
    """Teams identities, resolvable by Teams id or by Azure AD account.

    Two indexes over one list rather than two lists: a row reachable by one key
    and not the other would resolve or refuse depending on which call site asked,
    which is the kind of inconsistency nobody finds until an approval is refused
    for the wrong reason.
    """

    identities: tuple[ChatIdentity, ...] = ()
    #: Azure AD object id or user principal name, to the same principal.
    accounts: Mapping[str, str] = field(default_factory=dict)
    roles: Mapping[str, Role] = field(default_factory=dict)

    async def identity_of(self, user: PlatformUser) -> ChatIdentity | None:
        """Return who ``user`` acts as here, by Teams id and then by account."""
        for identity in self.identities:
            if identity.key == user.key:
                return identity
        principal = self.accounts.get(user.email) if user.email else None
        if principal is None:
            return None
        return teams_identity(
            user_id=user.user_id,
            tenant_id=user.workspace_id,
            principal_id=principal,
            display_name=user.display_name,
        )

    async def permissions_of(self, identity: ChatIdentity) -> frozenset[Permission]:
        """Return everything ``identity``'s principal may do."""
        role = self.roles.get(identity.principal_id)
        return permissions_for(role) if role is not None else frozenset()


def directory_of(
    rows: Sequence[Mapping[str, str]],
    roles: Mapping[str, Role],
    *,
    accounts: Mapping[str, str] | None = None,
) -> TeamsIdentityDirectory:
    """Return the Teams directory a deployment's configured rows describe."""
    return TeamsIdentityDirectory(
        identities=tuple(
            teams_identity(
                user_id=str(row["user_id"]),
                tenant_id=str(row.get("tenant_id", "")),
                principal_id=str(row["principal_id"]),
                node_id=str(row.get("node_id", "")),
                display_name=str(row.get("display_name", "")),
            )
            for row in rows
        ),
        accounts=dict(accounts or {}),
        roles=dict(roles),
    )


def account_of(member: Mapping[str, str]) -> str:
    """Return the account identifier a roster lookup answered with."""
    return str(member.get("aadObjectId") or member.get("userPrincipalName") or "")


__all__ = [
    "TeamsIdentityDirectory",
    "account_of",
    "directory_of",
    "teams_identity",
    "teams_user",
]
