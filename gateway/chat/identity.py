"""A platform user, a NinjaSRE principal, and the deliberate absence of a bridge.

There is no auto-provisioning here and that is the design. Anyone who can type
in a workspace could otherwise acquire a principal by typing, and the first
person to notice would be whoever reviewed the audit log afterwards. So an
unmapped user is refused, and the refusal is written to be actionable: it names
the platform, the identifier an operator has to map, and the *cheapest* role
that would have been enough — asking for ``responder`` gets approved, asking for
``owner`` does not.

**Two failures, deliberately not one.** ``UnmappedChatUser`` means "we do not
know who you are"; ``PermissionDenied`` means "we know, and you may not". They
lead to different next actions — get mapped, or get granted — and a surface that
reported both as "denied" would send everybody down the wrong one.

**Read-only interaction is a separate decision.** A deployment may let anyone in
a routed channel see what a run is doing without being mapped, and that is what
``anonymous_reads`` is. It is off unless an operator turns it on: a default that
shipped open would make the mapping requirement decorative.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from gateway.chat.port import ChatError, PlatformUser
from platform.identity.errors import PermissionDenied
from platform.identity.permissions import Permission, Role, permissions_for, roles_granting
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatIdentity:
    """One platform user, mapped to the principal they act as here.

    ``node_id`` is where in the organisation that principal's permissions are
    resolved. A chat identity without one resolves against the organisation as
    a whole, which is the narrow answer rather than the wide one — the same
    direction ``PermissionSet`` fails in.
    """

    platform: str
    platform_user_id: str
    principal_id: str
    workspace_id: str = ""
    node_id: str = ""
    display_name: str = ""

    @property
    def key(self) -> str:
        """Return the identifier this identity is looked up by."""
        return f"{self.platform}:{self.workspace_id}:{self.platform_user_id}"


class UnmappedChatUser(ChatError):
    """Nobody has mapped this platform user to a principal.

    Carries the user rather than only their identifier, so the refusal a surface
    shows can be built from the exception instead of from a second lookup.
    """

    def __init__(self, user: PlatformUser, permission: Permission | None = None) -> None:
        self.user = user
        self.permission = permission
        super().__init__(refusal_message(user, permission))


def refusal_message(user: PlatformUser, permission: Permission | None = None) -> str:
    """Return what an unmapped user is told, and what to do about it.

    Names the cheapest role that grants ``permission``. A denial that asked for
    the most privileged role would be a denial an admin refuses.
    """
    who = f"{user.display_name} ({user.user_id})" if user.display_name else user.user_id
    head = (
        f"{who} on {user.platform} is not mapped to a NinjaSRE principal, so this cannot "
        f"be done from chat."
    )
    if permission is None:
        return (
            f"{head} Ask an operator to map {user.platform} user {user.user_id!r} to your "
            f"NinjaSRE account."
        )
    cheapest = roles_granting(permission)
    role = cheapest[0].value if cheapest else Role.OPERATOR.value
    return (
        f"{head} {permission.value} needs the {role} role. Ask an operator to map "
        f"{user.platform} user {user.user_id!r} to your NinjaSRE account and grant it "
        f"{role} at the team this channel serves."
    )


@runtime_checkable
class IdentityDirectory(Protocol):
    """Where the platform-user-to-principal mapping is kept.

    A protocol because the mapping's home is a deployment decision — a
    configuration file for a small install, the identity store for a large one —
    and because the whole refusal path has to be testable without either.
    """

    async def identity_of(self, user: PlatformUser) -> ChatIdentity | None:
        """Return who ``user`` acts as here, or ``None`` if nobody has said."""

    async def permissions_of(self, identity: ChatIdentity) -> frozenset[Permission]:
        """Return everything ``identity``'s principal may do at its node."""


@dataclass(frozen=True, slots=True)
class MappingIdentityDirectory:
    """The mapping an operator wrote down, and nothing else.

    The shipped directory. It cannot grow an identity at runtime, which is the
    property that makes "no auto-provisioning" structural rather than a rule
    somebody has to keep following.
    """

    identities: tuple[ChatIdentity, ...] = ()
    roles: Mapping[str, Role] = field(default_factory=dict)

    async def identity_of(self, user: PlatformUser) -> ChatIdentity | None:
        """Return who ``user`` acts as here, or ``None``."""
        for identity in self.identities:
            if identity.key == user.key:
                return identity
        return None

    async def permissions_of(self, identity: ChatIdentity) -> frozenset[Permission]:
        """Return everything ``identity``'s principal may do."""
        role = self.roles.get(identity.principal_id)
        return permissions_for(role) if role is not None else frozenset()


@dataclass(frozen=True, slots=True)
class IdentityResolver:
    """The one place a chat action is turned into an authorised principal."""

    directory: IdentityDirectory
    #: Whether an unmapped user may still see what a run is doing. Off by
    #: default: a read is still a disclosure, and which channels are safe for
    #: one is an operator's decision.
    anonymous_reads: bool = False

    async def resolve(self, user: PlatformUser) -> ChatIdentity:
        """Return who ``user`` acts as.

        Raises:
            UnmappedChatUser: nobody has mapped them.
        """
        identity = await self.directory.identity_of(user)
        if identity is None:
            logger.info("chat.identity_unmapped", platform=user.platform, user_id=user.user_id)
            raise UnmappedChatUser(user)
        return identity

    async def authorise(self, user: PlatformUser, permission: Permission) -> ChatIdentity:
        """Return who ``user`` acts as, having checked they may do ``permission``.

        Raises:
            UnmappedChatUser: nobody has mapped them.
            PermissionDenied: they are mapped and do not hold ``permission``.
        """
        identity = await self.directory.identity_of(user)
        if identity is None:
            logger.info(
                "chat.privileged_action_refused",
                platform=user.platform,
                user_id=user.user_id,
                permission=permission.value,
            )
            raise UnmappedChatUser(user, permission)
        held = await self.directory.permissions_of(identity)
        if permission not in held:
            raise PermissionDenied(
                permission, node_id=identity.node_id or None, principal_id=identity.principal_id
            )
        return identity

    async def may(self, user: PlatformUser, permission: Permission) -> bool:
        """Return whether ``user`` may do ``permission``, without raising.

        The plan's flowchart in one method: an unmapped user gets the read-only
        answer where a deployment configured one, and ``False`` for anything
        that changes something.
        """
        identity = await self.directory.identity_of(user)
        if identity is None:
            return self.anonymous_reads and permission.is_read_only
        return permission in await self.directory.permissions_of(identity)


def directory_of(
    rows: Sequence[Mapping[str, str]], roles: Mapping[str, Role]
) -> MappingIdentityDirectory:
    """Return the directory a deployment's configured mapping describes."""
    return MappingIdentityDirectory(
        identities=tuple(
            ChatIdentity(
                platform=str(row["platform"]),
                platform_user_id=str(row["platform_user_id"]),
                principal_id=str(row["principal_id"]),
                workspace_id=str(row.get("workspace_id", "")),
                node_id=str(row.get("node_id", "")),
                display_name=str(row.get("display_name", "")),
            )
            for row in rows
        ),
        roles=dict(roles),
    )


__all__ = [
    "ChatIdentity",
    "IdentityDirectory",
    "IdentityResolver",
    "MappingIdentityDirectory",
    "UnmappedChatUser",
    "directory_of",
    "refusal_message",
]
