"""The identity layer's own view of a principal, a grant, a token, and a session.

These types sit above the persistence records rather than replacing them. The
store's ``User``, ``ApiToken``, and ``RoleBinding`` are rows; the types here are
what the rest of the platform reasons about, and the difference is not
ceremonial:

- a **``Principal``** is a human *or* a token, because everything above this
  layer asks "who did this" and must not have to ask "which of the two kinds of
  who";
- a **``Grant``** holds a ``Role``, not a string, so a role that no longer
  exists fails when the row is read rather than when a permission is checked;
- an **``IssuedToken``** carries the plaintext exactly once, in a value nobody
  is tempted to store, because there is no field on the record that could hold
  it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config.constants.security import API_TOKEN_HINT_CHARS, API_TOKEN_PREFIX
from platform.identity.errors import UnknownRole
from platform.identity.permissions import Permission, Role, permissions_for
from platform.persistence.ports import ActorKind, ApiToken, PrincipalKind, RoleBinding, User


@dataclass(frozen=True, slots=True)
class Principal:
    """Whoever is acting: a signed-in human, or a token acting for one.

    A token's principal keeps the owning user's id. "The payments bot did this"
    is not an answer anybody can follow up on; "Ada's payments bot did this" is,
    and ``token_id`` is what distinguishes the bot from Ada at a keyboard.
    """

    principal_id: str
    org_id: str
    kind: PrincipalKind = PrincipalKind.USER
    display_name: str = ""
    email: str | None = None
    is_active: bool = True
    token_id: str | None = None
    node_id: str | None = None

    @classmethod
    def of_user(cls, user: User, *, org_id: str) -> Principal:
        """Return the principal a signed-in human presents as."""
        return cls(
            principal_id=user.user_id,
            org_id=org_id,
            kind=user.kind,
            display_name=user.display_name,
            email=user.email,
            is_active=user.is_active,
        )

    @classmethod
    def of_token(cls, token: ApiToken, *, org_id: str, owner: User | None = None) -> Principal:
        """Return the principal a bearer token presents as."""
        return cls(
            principal_id=token.user_id,
            org_id=org_id,
            kind=owner.kind if owner is not None else PrincipalKind.SERVICE_ACCOUNT,
            display_name=owner.display_name if owner is not None else token.name,
            email=owner.email if owner is not None else None,
            is_active=owner.is_active if owner is not None else True,
            token_id=token.token_id,
            node_id=token.team_node_id,
        )

    @property
    def is_machine(self) -> bool:
        """Return whether this principal arrived as a token rather than a session."""
        return self.token_id is not None

    @property
    def actor_kind(self) -> ActorKind:
        """Return how the audit trail names this principal."""
        return ActorKind.TOKEN if self.is_machine else ActorKind.USER


@dataclass(frozen=True, slots=True)
class Grant:
    """A role held by a principal at a node, inherited by that node's descendants.

    ``node_id`` of ``None`` means the organisation as a whole. That is a
    different thing from a grant at the root node, and the difference matters
    when a tenant's tree is reshaped: an organisation-wide grant survives the
    root being renamed, and a grant at a node does not survive the node going
    away.
    """

    grant_id: str
    principal_id: str
    role: Role
    node_id: str | None = None
    granted_at: datetime | None = None

    @classmethod
    def of_binding(cls, binding: RoleBinding) -> Grant:
        """Return the grant ``binding`` records, or raise naming the unknown role."""
        try:
            role = Role(binding.role)
        except ValueError as unknown:
            raise UnknownRole(binding.role) from unknown
        return cls(
            grant_id=binding.binding_id,
            principal_id=binding.user_id,
            role=role,
            node_id=binding.node_id,
            granted_at=binding.granted_at,
        )

    def to_binding(self) -> RoleBinding:
        """Return the row this grant is stored as."""
        return RoleBinding(
            binding_id=self.grant_id,
            user_id=self.principal_id,
            role=self.role.value,
            node_id=self.node_id,
            granted_at=self.granted_at,
        )

    @property
    def permissions(self) -> frozenset[Permission]:
        """Return everything this grant confers at its node and below."""
        return permissions_for(self.role)


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """The result of issuing a token: the stored record, and the secret, once.

    ``secret`` exists on this value and nowhere else. It is not on ``ApiToken``,
    it is not written to storage, and it is not recoverable — showing it a second
    time would mean it had been kept, and it is not.
    """

    token: ApiToken
    secret: str

    @property
    def hint(self) -> str:
        """Return the prefix a listing shows to tell two tokens apart."""
        body = self.secret.removeprefix(API_TOKEN_PREFIX)
        return f"{API_TOKEN_PREFIX}{body[:API_TOKEN_HINT_CHARS]}…"


@dataclass(frozen=True, slots=True)
class Session:
    """An authenticated human session, bounded twice.

    Both bounds are carried on the value rather than recomputed by whoever
    validates it. A session that has to be re-derived is a session two callers
    can disagree about, and the one that disagrees generously is the bug.
    """

    session_id: str
    principal_id: str
    org_id: str
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    node_id: str | None = None
    break_glass: bool = False
    #: What the sign-in produced, kept so a re-evaluation at the next sign-in
    #: has something to compare against.
    groups: tuple[str, ...] = field(default_factory=tuple)

    def idle_for(self, now: datetime) -> timedelta:
        """Return how long this session has gone untouched."""
        return now - self.last_seen_at

    def is_expired(self, now: datetime, *, idle_timeout: timedelta) -> bool:
        """Return whether either bound has been crossed."""
        return now >= self.expires_at or self.idle_for(now) >= idle_timeout


__all__ = ["Grant", "IssuedToken", "Principal", "Session"]
