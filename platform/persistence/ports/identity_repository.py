"""Who is asking, and what they are allowed to ask for.

The store never sees a token. Callers hash the presented token and pass the
hash, so a database dump — or a query echo, or a row in a log — contains
nothing that can be replayed against the API. That is a property of the port's
signature rather than of an implementation's discipline: there is no method
here that accepts a token's plaintext, so there is no path by which one is
stored.

Resolving a token is the one identity operation that cannot be tenant-scoped,
for the obvious reason that resolving it is how the tenant becomes known. It
lives on ``TokenDirectory``, reached only through the system unit of work, and
it returns the scope the caller should then open — which is what makes "the
ports take no organisation argument" workable rather than merely strict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class PrincipalKind(StrEnum):
    """What kind of actor a record belongs to."""

    USER = "user"
    SERVICE_ACCOUNT = "service_account"


@dataclass(frozen=True, slots=True)
class User:
    """A person or service account within one organisation."""

    user_id: str
    email: str
    display_name: str
    kind: PrincipalKind = PrincipalKind.USER
    is_active: bool = True
    external_subject: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApiToken:
    """A bearer token, recorded by hash and never by value.

    ``token_hash`` is what the caller computed from the presented secret. The
    store treats it as an opaque identifier: it never hashes, never compares in
    a way that depends on the algorithm, and therefore never needs to change
    when the hashing does.

    ``team_node_id`` is the node the token may act within, and ``scopes`` the
    permissions it holds there. Both are stored rather than derived from the
    owning user, because a token is a credential in its own right: narrowing it
    to less than its owner holds is the point, and a token that silently gained
    permissions when its owner was promoted would defeat that.

    ``last_used_at`` is what makes an inactivity policy possible. It is written
    coarsely — a caller updates it when the recorded value has gone stale, not
    on every request — because the question it answers is "has this been used
    this month", and paying for a write per authenticated request to answer it
    would be the most expensive column in the deployment.
    """

    token_id: str
    user_id: str
    name: str
    token_hash: str
    scopes: tuple[str, ...] = ()
    team_node_id: str | None = None
    description: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        """Return whether this token has been revoked."""
        return self.revoked_at is not None


@dataclass(frozen=True, slots=True)
class RoleBinding:
    """A role granted to a principal, at a point in the hierarchy.

    ``node_id`` is where the grant applies. A binding at a team node covers
    everything beneath it; a binding at the organisation root covers the tenant.
    Feature 014 decides what each role permits — this port only records that the
    grant exists.
    """

    binding_id: str
    user_id: str
    role: str
    node_id: str | None = None
    granted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TokenResolution:
    """What a valid token identifies: a principal and the scope to open for it."""

    user_id: str
    org_id: str
    token_id: str
    team_node_id: str | None = None
    scopes: tuple[str, ...] = ()


@runtime_checkable
class IdentityRepository(Protocol):
    """Users, their tokens, and their role bindings, within one tenant."""

    async def get_user(self, user_id: str) -> User | None:
        """Return the user with ``user_id``, or ``None`` if this tenant has none."""

    async def find_user_by_email(self, email: str) -> User | None:
        """Return the user with ``email``, or ``None``. Matching is case-insensitive."""

    async def find_user_by_subject(self, external_subject: str) -> User | None:
        """Return the user bound to an SSO subject identifier, or ``None``."""

    async def upsert_user(self, user: User) -> User:
        """Store ``user`` and return it as stored."""

    async def list_users(self) -> tuple[User, ...]:
        """Return every user in this tenant, ordered by email."""

    async def store_token(self, token: ApiToken) -> ApiToken:
        """Store ``token`` by hash and return it.

        Raises ``DuplicateRecord`` if the hash is already recorded, which is how
        a token-generation collision surfaces as a failure rather than as two
        principals sharing a credential.
        """

    async def revoke_token(self, token_id: str, *, revoked_at: datetime) -> bool:
        """Mark ``token_id`` revoked and return whether it existed and was live."""

    async def revoke_tokens(
        self, token_ids: Sequence[str], *, revoked_at: datetime
    ) -> tuple[str, ...]:
        """Revoke every id in ``token_ids`` and return those that were live.

        One statement rather than a loop, because incident response revokes a
        team's tokens at once and a partial revocation that failed halfway is
        worse than one that failed outright.
        """

    async def tokens_for_user(self, user_id: str) -> tuple[ApiToken, ...]:
        """Return the user's tokens, newest first, revoked ones included."""

    async def list_tokens(self) -> tuple[ApiToken, ...]:
        """Return every token in this tenant, newest first, revoked ones included.

        What the inactivity policy and the expiry-warning sweep read. Bounded by
        the tenant rather than paged: a deployment whose token count does not fit
        in one answer has a problem this method is not the place to solve.
        """

    async def record_token_use(self, token_id: str, *, used_at: datetime) -> bool:
        """Record that ``token_id`` was used, and return whether it existed.

        Callers write coarsely — see ``ApiToken.last_used_at``. The store does
        not deduplicate, because deciding how stale is stale enough is a policy
        and this is not where policy lives.
        """

    async def upsert_role_binding(self, binding: RoleBinding) -> RoleBinding:
        """Store ``binding`` and return it as stored."""

    async def role_bindings_for_user(self, user_id: str) -> tuple[RoleBinding, ...]:
        """Return every role binding held by ``user_id``."""

    async def remove_role_binding(self, binding_id: str) -> bool:
        """Remove ``binding_id`` and return whether it existed."""


@dataclass(frozen=True, slots=True)
class TokenLocation:
    """Where a token hash lives, whether or not the token is usable.

    Exists for one caller: the audit trail. ``resolve_token`` deliberately
    refuses to say whether a rejected token was unknown, revoked, or expired,
    and that refusal is right on the authentication path — it is also why a
    rejected attempt would otherwise have no tenant to be recorded against.
    Locating one afterwards is what makes "the attempt is audited" possible
    without weakening the answer the authentication path gives.
    """

    org_id: str
    token: ApiToken


@runtime_checkable
class TokenDirectory(Protocol):
    """Token resolution, reached only through the system unit of work.

    One operation, because one is all that genuinely cannot know its tenant in
    advance. Anything else that wants to be here should be asked why it does not
    already have a scope.
    """

    async def resolve_token(self, token_hash: str, *, now: datetime) -> TokenResolution | None:
        """Return what ``token_hash`` identifies, or ``None``.

        ``None`` covers unknown, revoked, and expired without distinguishing
        them. The caller is about to reject the request either way, and a
        different message for each would tell an attacker which of their guesses
        was a real token.
        """

    async def find_token_by_hash(self, token_hash: str) -> TokenLocation | None:
        """Return where ``token_hash`` lives, ignoring whether it is usable.

        **Never authenticate with this.** It answers "does this hash exist and
        in which tenant", which is exactly the question ``resolve_token``
        declines to answer, and the only legitimate caller is the one writing
        the audit row for a rejection it has already decided on.
        """


__all__ = [
    "ApiToken",
    "IdentityRepository",
    "PrincipalKind",
    "RoleBinding",
    "TokenDirectory",
    "TokenLocation",
    "TokenResolution",
    "User",
]
