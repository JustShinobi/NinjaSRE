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
    """A person or service account within one organisation.

    ``email`` is ``""`` for a principal that has none — the bootstrap service
    account, and any other service account nobody gave an address. That is a
    legitimate value, not a placeholder waiting to be filled in, and it is
    **not** unique: a deployment may hold any number of principals with no
    address at all. Uniqueness applies only between two principals that both
    have one, compared case-insensitively. ``find_user_by_email("")`` never
    matches an addressless principal, on either backend — searching for
    nothing is not the same question as searching for something nobody has.
    """

    user_id: str
    email: str
    display_name: str
    kind: PrincipalKind = PrincipalKind.USER
    is_active: bool = True
    external_subject: str | None = None
    created_at: datetime | None = None
    #: The stored form of a local sign-in passphrase, for a person created
    #: with one — never the passphrase itself. ``None`` for a principal that
    #: has no local password: the environment-configured account (which never
    #: writes this row at all) and anyone who signs in through an identity
    #: provider instead. Set once, through ``IdentityRepository.set_local_password``,
    #: never through ``upsert_user`` — a general-purpose upsert that also
    #: carried this field would silently wipe it on the next unrelated update.
    local_password_hash: str | None = None


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
    #: Whether an empty ``scopes`` means "as wide as the owner" (``True``) or
    #: "holds nothing" (``False``). The two calls that mean the former — a
    #: browser sign-in and the durable credential issued right after the
    #: bootstrap one — ask for it explicitly; every other caller, machine-token
    #: issuance included, gets the safe reading of an empty scope list without
    #: asking for it.
    unscoped: bool = False

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


@dataclass(frozen=True, slots=True)
class LocalSignInOpening:
    """The one fact that decides whether this deployment's local sign-in exists.

    One row per deployment, ever. Its presence — not an account, not a stored
    passphrase — is the door: a principal created through
    ``POST /identity/principals`` stores a passphrase of its own without
    opening anything, and only a deliberate act (the CLI's administrator
    command, or exchanging the bootstrap credential) writes this row. Once
    written, it is never removed and never rewritten — there is no method on
    this port that updates or deletes one, because the fact it records does
    not stop being true.
    """

    opened_at: datetime
    #: Which of the two deliberate acts wrote this row. Free text describing a
    #: closed set (``"cli"``, ``"bootstrap-exchange"``) rather than an enum
    #: here, so a third path this feature does not know about still records
    #: something readable instead of failing to serialise.
    opened_via: str


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

    async def set_local_password(self, user_id: str, *, password_hash: str) -> bool:
        """Store the hash of a person's local passphrase, and return whether they existed.

        A targeted write, deliberately apart from ``upsert_user``: the two
        differ in every call except the one that creates the person, and a
        caller updating a display name or a status must never be able to
        clear this by omission.
        """

    async def upsert_role_binding(self, binding: RoleBinding) -> RoleBinding:
        """Store ``binding`` and return it as stored."""

    async def role_bindings_for_user(self, user_id: str) -> tuple[RoleBinding, ...]:
        """Return every role binding held by ``user_id``."""

    async def remove_role_binding(self, binding_id: str) -> bool:
        """Remove ``binding_id`` and return whether it existed."""

    async def local_sign_in_opening(self) -> LocalSignInOpening | None:
        """Return this deployment's opening record, or ``None`` if it has never opened."""

    async def open_local_sign_in(
        self, *, opened_at: datetime, opened_via: str
    ) -> LocalSignInOpening:
        """Record that the local sign-in door has been opened, once, and return the record.

        Raises ``DuplicateRecord`` when a record already exists — the arbiter
        of a race between two callers both trying to be first. The record
        already there is unchanged either way; a caller that loses reads it
        back with ``local_sign_in_opening`` rather than trusting what it tried
        to write.
        """


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
    "LocalSignInOpening",
    "PrincipalKind",
    "RoleBinding",
    "TokenDirectory",
    "TokenLocation",
    "TokenResolution",
    "User",
]
