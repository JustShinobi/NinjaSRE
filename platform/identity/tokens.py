"""Machine credentials: issued once, verified cheaply, revoked immediately.

**The secret exists for one call.** ``issue`` returns it, the store never sees
it, and nothing keeps it. Showing it a second time would mean it had been kept,
and a deployment whose database can reproduce its own bearer tokens has a
database dump problem rather than a token problem.

**The stored value is a keyed hash rather than a per-token salted one.** Salting
defends a low-entropy secret against a precomputed table; these secrets are 256
random bits, which no table covers. What a per-token salt *would* cost is the
constant-time lookup — resolution happens before the tenant is known, so it has
to be a single indexed read of one hash, and a per-row salt turns that into a
scan of every token in the deployment. The deployment-wide pepper keeps the
lookup and still means a stolen database is not a set of working credentials.

**Revocation is immediate, and that is a claim about the cache.** Resolutions are
cached for a few seconds because every authenticated request pays for one;
``revoke`` invalidates the entry before it returns, so the short TTL is the
backstop for a replica that missed the invalidation, never the mechanism, and
the security suite asserts the difference.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from config.constants.security import (
    API_TOKEN_DEFAULT_LIFETIME_DAYS,
    API_TOKEN_MAX_LIFETIME_DAYS,
    API_TOKEN_PREFIX,
    API_TOKEN_SECRET_BYTES,
    IDENTITY_AUDIT_RESOURCE_KIND_TOKEN,
    MAX_BULK_REVOCATIONS,
    MAX_CACHED_TOKEN_RESOLUTIONS,
    TOKEN_AUDIT_ACTION_EXPIRY_WARNING,
    TOKEN_AUDIT_ACTION_ISSUE,
    TOKEN_AUDIT_ACTION_REJECT,
    TOKEN_AUDIT_ACTION_REVOKE,
    TOKEN_CLOCK_SKEW_SECONDS,
    TOKEN_EXPIRY_WARNING_DAYS,
    TOKEN_INACTIVITY_REVOCATION_DAYS,
    TOKEN_RESOLUTION_CACHE_TTL_SECONDS,
)
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.authorisation import PermissionSet, load_permissions
from platform.identity.errors import (
    TokenLifetimeTooLong,
    TokenRejected,
    TooManyRevocations,
)
from platform.identity.models import IssuedToken, Principal
from platform.identity.permissions import Permission
from platform.persistence.ports import (
    ActorKind,
    ApiToken,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
    TokenResolution,
)

#: How stale ``last_used_at`` may get before a use is written back. A day,
#: because the only question the column answers is measured in months
#: (``TOKEN_INACTIVITY_REVOCATION_DAYS``) and writing on every request would make
#: it the busiest column in the deployment for no gain in the answer.
LAST_USED_WRITE_INTERVAL = timedelta(days=1)

CLOCK_SKEW = timedelta(seconds=TOKEN_CLOCK_SKEW_SECONDS)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TokenHasher:
    """Turns a presented secret into the value the store holds.

    ``pepper`` is deployment-wide and lives wherever the operator keeps secrets
    — it is not in the database, which is the entire point: a dump without it is
    a list of hashes nobody can use.
    """

    pepper: bytes = b""

    def hash(self, secret: str) -> str:
        """Return the stored representation of ``secret``."""
        material = secret.encode("utf-8")
        if not self.pepper:
            return hashlib.sha256(material).hexdigest()
        return hmac.new(self.pepper, material, hashlib.sha256).hexdigest()

    def generate(self) -> str:
        """Return a new secret, prefixed so a leak is recognisable as ours."""
        return f"{API_TOKEN_PREFIX}{secrets.token_urlsafe(API_TOKEN_SECRET_BYTES)}"


@dataclass(slots=True)
class ResolutionCache:
    """Caches token resolutions for a few seconds, and forgets one on demand.

    Bounded, and the bound matters: an unbounded cache keyed by presented hash
    is a memory leak an attacker drives by presenting garbage. Eviction is
    oldest-first, which is right for a cache whose entries all expire in the
    same handful of seconds anyway.
    """

    ttl: timedelta = timedelta(seconds=TOKEN_RESOLUTION_CACHE_TTL_SECONDS)
    max_entries: int = MAX_CACHED_TOKEN_RESOLUTIONS
    _entries: dict[str, tuple[datetime, TokenResolution]] = field(default_factory=dict)
    _by_token: dict[str, str] = field(default_factory=dict)

    def get(self, token_hash: str, *, now: datetime) -> TokenResolution | None:
        """Return the cached resolution if it is still fresh."""
        found = self._entries.get(token_hash)
        if found is None:
            return None
        cached_at, resolution = found
        if now - cached_at >= self.ttl:
            self.forget(resolution.token_id)
            return None
        return resolution

    def put(self, token_hash: str, resolution: TokenResolution, *, now: datetime) -> None:
        """Cache ``resolution``, evicting the oldest entry if the bound is reached."""
        if token_hash not in self._entries and len(self._entries) >= self.max_entries:
            oldest = next(iter(self._entries))
            self._drop(oldest)
        self._entries[token_hash] = (now, resolution)
        self._by_token[resolution.token_id] = token_hash

    def forget(self, token_id: str) -> None:
        """Drop the entry for ``token_id``, so the next request re-resolves it."""
        token_hash = self._by_token.pop(token_id, None)
        if token_hash is not None:
            self._entries.pop(token_hash, None)

    def forget_all(self, token_ids: Iterable[str]) -> None:
        """Drop several entries, for a bulk revocation."""
        for token_id in token_ids:
            self.forget(token_id)

    def _drop(self, token_hash: str) -> None:
        """Remove one entry and its reverse index."""
        entry = self._entries.pop(token_hash, None)
        if entry is not None:
            self._by_token.pop(entry[1].token_id, None)


@dataclass(frozen=True, slots=True)
class AuthenticatedToken:
    """What a valid bearer token resolves to: a principal and what it may do."""

    principal: Principal
    permissions: PermissionSet
    scope: TenantScope
    token: ApiToken


@dataclass(frozen=True, slots=True)
class TokenNotice:
    """A token something should be said about, and who to say it to."""

    token: ApiToken
    owner_id: str
    reason: str


@dataclass(slots=True)
class TokenService:
    """Issues, verifies, revokes, and sweeps machine credentials."""

    gateway: PersistenceGateway
    hasher: TokenHasher = field(default_factory=TokenHasher)
    recorder: AuditRecorder | None = None
    cache: ResolutionCache = field(default_factory=ResolutionCache)
    clock: Callable[[], datetime] = _utc_now

    # --- Issuing --------------------------------------------------------------

    async def issue(
        self,
        scope: TenantScope,
        context: AuditContext,
        *,
        user_id: str,
        name: str,
        node_id: str | None = None,
        permissions: Sequence[Permission] = (),
        description: str | None = None,
        lifetime_days: int | None = None,
        lifetime: timedelta | None = None,
        supersede: bool = False,
        supersede_expired_only: bool = False,
        unscoped: bool = False,
    ) -> IssuedToken:
        """Return a new token, its plaintext included exactly once.

        ``permissions`` is a ceiling, not a grant. It narrows what the owning
        user already holds; a token can never do something its owner cannot,
        which is why there is no path here that consults the role catalogue.
        An empty ``permissions`` means the token holds nothing at all — not
        "everything its owner does" — unless ``unscoped`` says otherwise.

        ``unscoped`` is that otherwise. It is how a credential that stands in
        for a person rather than for one declared purpose — a browser sign-in,
        the durable credential issued right after the bootstrap one — keeps
        resolving to whatever its owner currently holds, dynamically, at every
        authentication. It defaults to ``False`` and has to be asked for: the
        machine-token issuance route never does, which is the whole point of
        it existing as its own flag rather than being read off an empty
        ``permissions`` list the way it used to be.

        ``lifetime`` overrides ``lifetime_days`` and is how a credential shorter
        than a day is issued. It exists for the bootstrap credential, which lives
        for an hour: expressing that as a fraction of a day would have meant
        either rounding it up to a day or teaching every caller that
        ``lifetime_days`` is sometimes not days. The ceiling applies to both.

        ``supersede`` revokes every live token already held by ``user_id`` under
        this same ``name`` and ``node_id`` — this issuance's *purpose* — instead
        of leaving them beside the new one. It defaults to ``False`` and has to
        be asked for, because "the same name" is also how a browser sign-in is
        issued (``platform/identity/local_accounts.py``'s ``CREDENTIAL_NAME``),
        and a second tab or a second device signing in must not revoke the
        first. Machine-token issuance (the console's own route) and the
        bootstrap credential (whose unrevoked, merely-expired rows are exactly
        what accumulated before this existed) both ask for it.

        ``supersede_expired_only`` narrows that to the rows it was introduced
        for. One deployment can be several containers of one image sharing one
        database — the standard compose profile is three — and each keeps its
        bootstrap credential in a host file of its own while the token lives in
        the database they share. The second container to start finds no
        credential of its own, issues one, and would supersede what it finds
        under the same name: the first container's, still live, and still the
        one an operator is told to read. The reasoning is the same one that
        keeps a second browser tab from revoking the first; only the thing
        starting twice is different.
        """
        if lifetime is not None:
            span = lifetime
        else:
            days = lifetime_days if lifetime_days is not None else API_TOKEN_DEFAULT_LIFETIME_DAYS
            if days < 1:
                raise TokenLifetimeTooLong(days, API_TOKEN_MAX_LIFETIME_DAYS)
            span = timedelta(days=days)

        if span > timedelta(days=API_TOKEN_MAX_LIFETIME_DAYS):
            raise TokenLifetimeTooLong(span.days, API_TOKEN_MAX_LIFETIME_DAYS)
        if span <= timedelta(0):
            raise TokenLifetimeTooLong(span.days, API_TOKEN_MAX_LIFETIME_DAYS)

        now = self.clock()
        secret = self.hasher.generate()
        record = ApiToken(
            token_id=secrets.token_hex(16),
            user_id=user_id,
            name=name,
            token_hash=self.hasher.hash(secret),
            scopes=tuple(permission.value for permission in permissions),
            team_node_id=node_id,
            description=description,
            created_at=now,
            expires_at=now + span,
            unscoped=unscoped,
        )

        superseded: tuple[str, ...] = ()
        async with self.gateway.begin(scope) as uow:
            if supersede:
                existing = await uow.identity.tokens_for_user(user_id)
                superseded = tuple(
                    token.token_id
                    for token in existing
                    if not token.is_revoked
                    and token.name == name
                    and token.team_node_id == node_id
                    and not (
                        supersede_expired_only
                        and token.expires_at is not None
                        and token.expires_at > now
                    )
                )
                if superseded:
                    await uow.identity.revoke_tokens(superseded, revoked_at=now)
            stored = await uow.identity.store_token(record)

        if superseded:
            self.cache.forget_all(superseded)
            for token_id in superseded:
                await self._audit(
                    scope,
                    context,
                    action=TOKEN_AUDIT_ACTION_REVOKE,
                    resource_id=token_id,
                    detail={"reason": f"superseded by a new token issued for {name!r}"},
                )

        await self._audit(
            scope,
            context,
            action=TOKEN_AUDIT_ACTION_ISSUE,
            resource_id=stored.token_id,
            detail={
                "name": name,
                "team_node_id": node_id,
                "scopes": list(stored.scopes),
                "expires_at": stored.expires_at.isoformat() if stored.expires_at else None,
                **({"superseded": list(superseded)} if superseded else {}),
            },
        )
        return IssuedToken(token=stored, secret=secret, superseded=superseded)

    # --- Verifying ------------------------------------------------------------

    async def authenticate(self, secret: str) -> AuthenticatedToken:
        """Return who this token is, or raise ``TokenRejected``.

        Every rejection raises the same type carrying a different ``reason``. The
        reason is for the audit trail; a transport turns all of them into one
        response, because telling a caller their token was recognised but
        expired tells them the token was recognised.
        """
        now = self.clock()
        token_hash = self.hasher.hash(secret)

        resolution = self.cache.get(token_hash, now=now)
        if resolution is None:
            # Expiry is compared against a clock pushed back by the skew
            # tolerance, so a token that expired moments ago on another host's
            # clock still resolves. Revocation gets no such tolerance: the store
            # rejects a revoked token outright whatever instant it is handed.
            async with self.gateway.begin_system() as system:
                found = await system.tokens.resolve_token(token_hash, now=now - CLOCK_SKEW)
            if found is None:
                await self._reject(token_hash)
            resolution = found
            self.cache.put(token_hash, resolution, now=now)

        scope = TenantScope(org_id=resolution.org_id, team_node_id=resolution.team_node_id)
        async with self.gateway.begin(scope) as uow:
            owner = await uow.identity.get_user(resolution.user_id)
            record = next(
                (
                    token
                    for token in await uow.identity.tokens_for_user(resolution.user_id)
                    if token.token_id == resolution.token_id
                ),
                None,
            )
            node_exists = (
                resolution.team_node_id is None
                or await uow.config.get(resolution.team_node_id) is not None
            )
            permissions = await load_permissions(
                uow, resolution.user_id, node_id=resolution.team_node_id
            )

        # The team check is here rather than in the store because the store has
        # no view of the configuration hierarchy — and a token pointed at a node
        # that was deleted is the one rejection whose reason an operator has to
        # be told, since re-issuing will not fix it.
        if record is None or owner is None or not owner.is_active:
            await self._reject(token_hash, scope=scope)
        if not node_exists:
            await self._reject(token_hash, scope=scope, reason=_TEAM_GONE)

        await self._record_use(scope, record, now=now)
        return AuthenticatedToken(
            principal=Principal.of_token(record, org_id=resolution.org_id, owner=owner),
            permissions=_scoped(record, permissions),
            scope=scope,
            token=record,
        )

    # --- Revoking -------------------------------------------------------------

    async def revoke(self, scope: TenantScope, context: AuditContext, token_id: str) -> bool:
        """Revoke one token and return whether it was live.

        The cache entry is dropped before this returns, so the next request
        re-resolves and is refused. That ordering is the whole guarantee.
        """
        now = self.clock()
        async with self.gateway.begin(scope) as uow:
            changed = await uow.identity.revoke_token(token_id, revoked_at=now)
        self.cache.forget(token_id)

        if changed:
            await self._audit(
                scope,
                context,
                action=TOKEN_AUDIT_ACTION_REVOKE,
                resource_id=token_id,
                detail={"reason": "revoked by an operator"},
            )
        return changed

    async def revoke_all(
        self,
        scope: TenantScope,
        context: AuditContext,
        *,
        token_ids: Sequence[str] | None = None,
        user_id: str | None = None,
        node_id: str | None = None,
        reason: str = "bulk revocation",
    ) -> tuple[str, ...]:
        """Revoke a set of tokens at once and return those that were live.

        Selected by explicit ids, by owner, or by team. Bounded, because a single
        call that could revoke a whole deployment is not a control — an operator
        who genuinely means to do that can say so in batches, and each batch is
        an audit row.
        """
        wanted = await self._select(scope, token_ids=token_ids, user_id=user_id, node_id=node_id)
        if len(wanted) > MAX_BULK_REVOCATIONS:
            raise TooManyRevocations(len(wanted), MAX_BULK_REVOCATIONS)

        now = self.clock()
        async with self.gateway.begin(scope) as uow:
            revoked = await uow.identity.revoke_tokens(wanted, revoked_at=now)
        self.cache.forget_all(revoked)

        for token_id in revoked:
            await self._audit(
                scope,
                context,
                action=TOKEN_AUDIT_ACTION_REVOKE,
                resource_id=token_id,
                detail={"reason": reason},
            )
        return revoked

    # --- Policy ---------------------------------------------------------------

    async def sweep_inactive(
        self, scope: TenantScope, context: AuditContext
    ) -> tuple[TokenNotice, ...]:
        """Revoke tokens unused past the inactivity window and report their owners.

        Returns rather than notifies. Delivery belongs to the notification
        subsystem; what this owes is an accurate list and an audit row per
        revocation, and returning them keeps this module testable without one.
        """
        now = self.clock()
        cutoff = now - timedelta(days=TOKEN_INACTIVITY_REVOCATION_DAYS)
        async with self.gateway.begin(scope) as uow:
            candidates = await uow.identity.list_tokens()

        stale = tuple(
            token for token in candidates if not token.is_revoked and _last_activity(token) < cutoff
        )
        if not stale:
            return ()

        revoked = await self.revoke_all(
            scope,
            context,
            token_ids=tuple(token.token_id for token in stale),
            reason=f"inactive for more than {TOKEN_INACTIVITY_REVOCATION_DAYS} days",
        )
        by_id = {token.token_id: token for token in stale}
        return tuple(
            TokenNotice(
                token=by_id[token_id],
                owner_id=by_id[token_id].user_id,
                reason=f"inactive for more than {TOKEN_INACTIVITY_REVOCATION_DAYS} days",
            )
            for token_id in revoked
        )

    async def expiring_soon(self, scope: TenantScope) -> tuple[TokenNotice, ...]:
        """Return the live tokens whose expiry is inside the warning window."""
        now = self.clock()
        horizon = now + timedelta(days=TOKEN_EXPIRY_WARNING_DAYS)
        async with self.gateway.begin(scope) as uow:
            tokens = await uow.identity.list_tokens()

        return tuple(
            TokenNotice(
                token=token,
                owner_id=token.user_id,
                reason=f"expires within {TOKEN_EXPIRY_WARNING_DAYS} days",
            )
            for token in tokens
            if not token.is_revoked
            and token.expires_at is not None
            and now < token.expires_at <= horizon
        )

    async def warn_expiring(
        self, scope: TenantScope, context: AuditContext
    ) -> tuple[TokenNotice, ...]:
        """Report the tokens nearing expiry, and audit that they were warned about."""
        notices = await self.expiring_soon(scope)
        for notice in notices:
            await self._audit(
                scope,
                context,
                action=TOKEN_AUDIT_ACTION_EXPIRY_WARNING,
                resource_id=notice.token.token_id,
                detail={"owner_id": notice.owner_id, "reason": notice.reason},
            )
        return notices

    # --- Internals ------------------------------------------------------------

    async def _select(
        self,
        scope: TenantScope,
        *,
        token_ids: Sequence[str] | None,
        user_id: str | None,
        node_id: str | None,
    ) -> tuple[str, ...]:
        """Return the token ids a bulk revocation covers."""
        if token_ids is not None:
            return tuple(token_ids)
        async with self.gateway.begin(scope) as uow:
            tokens = (
                await uow.identity.tokens_for_user(user_id)
                if user_id is not None
                else await uow.identity.list_tokens()
            )
        return tuple(
            token.token_id
            for token in tokens
            if not token.is_revoked and (node_id is None or token.team_node_id == node_id)
        )

    async def _record_use(self, scope: TenantScope, token: ApiToken, *, now: datetime) -> None:
        """Write ``last_used_at`` back, but only when the stored value has gone stale."""
        previous = token.last_used_at
        if previous is not None and now - previous < LAST_USED_WRITE_INTERVAL:
            return
        async with self.gateway.begin(scope) as uow:
            await uow.identity.record_token_use(token.token_id, used_at=now)

    async def _audit(
        self,
        scope: TenantScope,
        context: AuditContext,
        *,
        action: str,
        resource_id: str,
        detail: dict[str, object] | None = None,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
    ) -> None:
        """Record one token-lifecycle event, if this service was given a recorder."""
        if self.recorder is None:
            return
        await self.recorder.record(
            scope,
            context,
            action=action,
            resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_TOKEN,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail or {},
        )

    async def _reject(
        self,
        token_hash: str,
        *,
        scope: TenantScope | None = None,
        reason: str | None = None,
    ) -> NoReturn:
        """Audit the refused attempt where it can be, and raise.

        The rejection is decided before this is called; locating the token is
        only so the record has a tenant to live in. A hash that belongs to no
        token is not audited at all, and deliberately: a deployment-wide table
        of unrecognised strings is somewhere an attacker writes at whatever rate
        they choose.
        """
        located = None
        if self.recorder is not None:
            async with self.gateway.begin_system() as system:
                located = await system.tokens.find_token_by_hash(token_hash)

        if located is None:
            raise TokenRejected(reason or _UNPLACEABLE)

        self.cache.forget(located.token.token_id)
        detail = reason or _describe(located.token, self.clock())
        if self.recorder is not None:
            await self.recorder.record(
                scope if scope is not None else TenantScope(org_id=located.org_id),
                AuditContext(actor_kind=ActorKind.TOKEN, actor_id=located.token.user_id),
                action=TOKEN_AUDIT_ACTION_REJECT,
                resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_TOKEN,
                resource_id=located.token.token_id,
                outcome=AuditOutcome.DENIED,
                detail={"reason": detail},
            )
        raise TokenRejected(detail, token_id=located.token.token_id)


#: The reasons a rejection carries. Prose rather than codes, because their only
#: readers are the audit trail and an operator reading it.
_UNPLACEABLE = "unknown, expired, or revoked"
_TEAM_GONE = "the team this token is scoped to no longer exists"


def _describe(token: ApiToken, now: datetime) -> str:
    """Return why a located token was refused, for the record only."""
    if token.is_revoked:
        return "revoked"
    if token.expires_at is not None and token.expires_at <= now - CLOCK_SKEW:
        return "expired"
    return "the owning principal is inactive or gone"


def _last_activity(token: ApiToken) -> datetime:
    """Return when a token was last used, falling back to when it was issued.

    A token issued and never used is inactive from the moment it was created,
    which is the reading an operator expects and the one a null ``last_used_at``
    would otherwise turn into "never inactive". A token with neither timestamp
    cannot be aged at all, so it is treated as brand new: the safe direction for
    a missing field is to leave a credential working rather than to revoke one
    for a reason nobody can reconstruct.
    """
    return token.last_used_at or token.created_at or datetime.max.replace(tzinfo=UTC)


def _scoped(token: ApiToken, held: PermissionSet) -> PermissionSet:
    """Return what ``token`` may do: its owner's permissions, capped by its scopes.

    ``token.unscoped`` is a personal access token's own flag and carries no
    cap — it is as wide as its owner and no wider. Every other token is capped
    by exactly what it was issued for, and an empty ``scopes`` caps it to
    nothing: ``PermissionSet.narrowed_to`` already draws that line at the
    permission-set layer (``ceiling=None`` is unbounded, ``ceiling=frozenset()``
    is bounded to nothing), and this is the one place that has to ask
    ``token.unscoped`` rather than reading emptiness as the unbounded case,
    because the two are indistinguishable once ``scopes`` alone is looked at.

    A stored scope naming a permission this build does not have is dropped
    rather than raising. The alternative is that renaming a permission breaks
    every token issued before the rename, at authentication time, across the
    whole deployment.
    """
    if token.unscoped:
        return held
    return held.narrowed_to(
        Permission(scope) for scope in token.scopes if scope in _PERMISSION_VALUES
    )


#: The catalogue as a set of strings, for the membership test above.
_PERMISSION_VALUES: frozenset[str] = frozenset(permission.value for permission in Permission)


__all__ = [
    "CLOCK_SKEW",
    "LAST_USED_WRITE_INTERVAL",
    "AuthenticatedToken",
    "ResolutionCache",
    "TokenHasher",
    "TokenNotice",
    "TokenService",
]
