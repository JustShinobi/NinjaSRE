"""Users, token hashes, and role bindings over PostgreSQL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants.persistence import LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY
from platform.persistence.errors import DuplicateRecord
from platform.persistence.ports.identity_repository import (
    ApiToken,
    LocalSignInOpening,
    PrincipalKind,
    RoleBinding,
    TokenLocation,
    TokenResolution,
    User,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.models import USERS_EMAIL_UNIQUE_INDEX_NAME
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    constraint_name_of,
    translating,
    utc_now,
)


def _to_user(row: models.User) -> User:
    return User(
        user_id=row.user_id,
        email=row.email,
        display_name=row.display_name,
        kind=PrincipalKind(row.kind),
        is_active=row.is_active,
        external_subject=row.external_subject,
        created_at=as_utc(row.created_at),
        local_password_hash=row.local_password_hash,
    )


def _to_token(row: models.ApiToken) -> ApiToken:
    return ApiToken(
        token_id=row.token_id,
        user_id=row.user_id,
        name=row.name,
        token_hash=row.token_hash,
        scopes=as_tuple(row.scopes),
        team_node_id=row.team_node_id,
        description=row.description,
        unscoped=row.unscoped,
        created_at=as_utc(row.created_at),
        expires_at=as_utc(row.expires_at),
        revoked_at=as_utc(row.revoked_at),
        last_used_at=as_utc(row.last_used_at),
    )


def _to_binding(row: models.RoleBinding) -> RoleBinding:
    return RoleBinding(
        binding_id=row.binding_id,
        user_id=row.user_id,
        role=row.role,
        node_id=row.node_id,
        granted_at=as_utc(row.granted_at),
    )


def _to_opening(row: models.LocalSignInOpening) -> LocalSignInOpening:
    # ``opened_at`` is NOT NULL: unlike the other timestamps in this module,
    # there is no "not yet happened" state for a row that exists at all.
    moment = row.opened_at
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return LocalSignInOpening(opened_at=aware.astimezone(UTC), opened_via=row.opened_via)


@dataclass(slots=True)
class PostgresIdentityRepository(TenantBound):
    """Users, tokens, and role bindings for one organisation."""

    async def get_user(self, user_id: str) -> User | None:
        """Return the user with ``user_id``, or ``None``."""
        row = await self.session.get(models.User, (self.org_id, user_id))
        return _to_user(row) if row is not None else None

    async def find_user_by_email(self, email: str) -> User | None:
        """Return the user with ``email``, or ``None``.

        An empty ``email`` never matches: ``email_folded`` is ``NULL`` for
        every principal with no address, and this returns before asking the
        database rather than relying on ``NULL`` never equalling ``NULL`` —
        a guard the fake needs explicitly is a guard worth being explicit
        about here too, rather than a coincidence of SQL's own semantics.
        """
        if not email:
            return None
        row = await self.session.scalar(
            select(models.User).where(
                models.User.org_id == self.org_id,
                models.User.email_folded == email.casefold(),
            )
        )
        return _to_user(row) if row is not None else None

    async def find_user_by_subject(self, external_subject: str) -> User | None:
        """Return the user bound to an SSO subject identifier, or ``None``."""
        row = await self.session.scalar(
            select(models.User).where(
                models.User.org_id == self.org_id,
                models.User.external_subject == external_subject,
            )
        )
        return _to_user(row) if row is not None else None

    async def upsert_user(self, user: User) -> User:
        """Store ``user`` and return it as stored.

        Raises ``DuplicateRecord`` naming ``user.email`` when another
        principal already holds it — the collision the unique index catches
        that a caller's own pre-check did not, because two callers reached
        it at the same instant. The error names the address that collided,
        never ``USERS_EMAIL_UNIQUE_INDEX_NAME``: the constraint name is read
        back only to tell this collision apart from any other ``23505`` this
        table could raise, and it goes no further than that ``if``.
        """
        row = await self.session.get(models.User, (self.org_id, user.user_id))
        if row is None:
            row = models.User(org_id=self.org_id, user_id=user.user_id)
            self.session.add(row)
            row.created_at = user.created_at or utc_now()
        elif user.created_at is not None:
            row.created_at = user.created_at

        row.email = user.email
        # Stored beside the address rather than derived in a functional index:
        # PostgreSQL's ``lower()`` and Python's ``casefold()`` disagree on
        # non-ASCII, and a uniqueness rule that disagrees with the lookup that
        # enforces it is worse than no rule. ``None`` for "no address" — never
        # the empty string — because it is ``NULL`` that the unique index
        # never treats as a collision between two rows that both carry it.
        row.email_folded = user.email.casefold() or None
        row.display_name = user.display_name
        row.kind = user.kind.value
        row.is_active = user.is_active
        row.external_subject = user.external_subject

        try:
            await self.session.flush()
        except IntegrityError as error:
            if constraint_name_of(error) == USERS_EMAIL_UNIQUE_INDEX_NAME:
                raise DuplicateRecord(kind="user", identifier=user.email) from error
            with translating(kind="user", identifier=user.user_id):
                raise
        return _to_user(row)

    async def list_users(self) -> tuple[User, ...]:
        """Return every user in this tenant, ordered by email."""
        rows = await self.session.scalars(
            select(models.User)
            .where(models.User.org_id == self.org_id)
            .order_by(models.User.email, models.User.user_id)
        )
        return tuple(_to_user(row) for row in rows)

    async def store_token(self, token: ApiToken) -> ApiToken:
        """Store ``token`` by hash and return it."""
        if await self.session.get(models.ApiToken, (self.org_id, token.token_id)) is not None:
            raise DuplicateRecord(kind="api token", identifier=token.token_id)

        row = models.ApiToken(
            org_id=self.org_id,
            token_id=token.token_id,
            user_id=token.user_id,
            name=token.name,
            token_hash=token.token_hash,
            scopes=as_list(token.scopes),
            team_node_id=token.team_node_id,
            description=token.description,
            unscoped=token.unscoped,
            created_at=token.created_at or utc_now(),
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
            last_used_at=token.last_used_at,
        )
        self.session.add(row)
        with translating(
            kind="api token hash",
            identifier=token.token_id,
            referenced="user",
            referenced_id=token.user_id,
        ):
            await self.session.flush()
        return _to_token(row)

    async def revoke_token(self, token_id: str, *, revoked_at: datetime) -> bool:
        """Mark ``token_id`` revoked and return whether it existed and was live."""
        row = await self.session.get(models.ApiToken, (self.org_id, token_id))
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = revoked_at
        await self.session.flush()
        return True

    async def revoke_tokens(
        self, token_ids: Sequence[str], *, revoked_at: datetime
    ) -> tuple[str, ...]:
        """Revoke every id in ``token_ids`` and return those that were live.

        One statement, and it reports what it changed rather than what it was
        asked to change: an id that was already revoked, or belongs to another
        tenant, is simply absent from the answer.
        """
        wanted = tuple(dict.fromkeys(token_ids))
        if not wanted:
            return ()
        revoked = await self.session.scalars(
            update(models.ApiToken)
            .where(
                models.ApiToken.org_id == self.org_id,
                models.ApiToken.token_id.in_(wanted),
                models.ApiToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
            .returning(models.ApiToken.token_id)
        )
        changed = frozenset(revoked)
        await self.session.flush()
        return tuple(token_id for token_id in wanted if token_id in changed)

    async def list_tokens(self) -> tuple[ApiToken, ...]:
        """Return every token in this tenant, newest first."""
        rows = await self.session.scalars(
            select(models.ApiToken)
            .where(models.ApiToken.org_id == self.org_id)
            .order_by(models.ApiToken.created_at.desc(), models.ApiToken.token_id.desc())
        )
        return tuple(_to_token(row) for row in rows)

    async def record_token_use(self, token_id: str, *, used_at: datetime) -> bool:
        """Record that ``token_id`` was used, and return whether it existed."""
        row = await self.session.get(models.ApiToken, (self.org_id, token_id))
        if row is None:
            return False
        row.last_used_at = used_at
        await self.session.flush()
        return True

    async def set_local_password(self, user_id: str, *, password_hash: str) -> bool:
        """Store the hash of a person's local passphrase, and return whether they existed."""
        row = await self.session.get(models.User, (self.org_id, user_id))
        if row is None:
            return False
        row.local_password_hash = password_hash
        await self.session.flush()
        return True

    async def tokens_for_user(self, user_id: str) -> tuple[ApiToken, ...]:
        """Return the user's tokens, newest first, revoked ones included."""
        rows = await self.session.scalars(
            select(models.ApiToken)
            .where(
                models.ApiToken.org_id == self.org_id,
                models.ApiToken.user_id == user_id,
            )
            .order_by(models.ApiToken.created_at.desc(), models.ApiToken.token_id.desc())
        )
        return tuple(_to_token(row) for row in rows)

    async def upsert_role_binding(self, binding: RoleBinding) -> RoleBinding:
        """Store ``binding`` and return it as stored."""
        row = await self.session.get(models.RoleBinding, (self.org_id, binding.binding_id))
        if row is None:
            row = models.RoleBinding(org_id=self.org_id, binding_id=binding.binding_id)
            self.session.add(row)
        row.user_id = binding.user_id
        row.role = binding.role
        row.node_id = binding.node_id
        row.granted_at = binding.granted_at or utc_now()

        with translating(
            kind="role binding",
            identifier=binding.binding_id,
            referenced="user",
            referenced_id=binding.user_id,
        ):
            await self.session.flush()
        return _to_binding(row)

    async def role_bindings_for_user(self, user_id: str) -> tuple[RoleBinding, ...]:
        """Return every role binding held by ``user_id``."""
        rows = await self.session.scalars(
            select(models.RoleBinding)
            .where(
                models.RoleBinding.org_id == self.org_id,
                models.RoleBinding.user_id == user_id,
            )
            .order_by(models.RoleBinding.role, models.RoleBinding.binding_id)
        )
        return tuple(_to_binding(row) for row in rows)

    async def remove_role_binding(self, binding_id: str) -> bool:
        """Remove ``binding_id`` and return whether it existed."""
        row = await self.session.get(models.RoleBinding, (self.org_id, binding_id))
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def local_sign_in_opening(self) -> LocalSignInOpening | None:
        """Return this deployment's opening record, or ``None`` if it has never opened."""
        row = await self.session.get(models.LocalSignInOpening, self.org_id)
        return _to_opening(row) if row is not None else None

    async def open_local_sign_in(
        self, *, opened_at: datetime, opened_via: str
    ) -> LocalSignInOpening:
        """Record that the local sign-in door has been opened, once.

        Held under the same kind of session-level advisory lock the schema
        migrator uses, with a key of its own: acquired, checked, inserted (or
        not) and released, so the check and the insert cannot straddle a
        second caller's own check and insert. That is what makes "insert and
        do not overwrite, read back, whichever caller reads somebody else's
        row lost" a property of this method rather than a race between two
        callers hoping a constraint catches them.
        """
        await self.session.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY},
        )
        try:
            existing = await self.session.get(models.LocalSignInOpening, self.org_id)
            if existing is not None:
                raise DuplicateRecord(kind="local sign-in opening", identifier=self.org_id)
            row = models.LocalSignInOpening(
                org_id=self.org_id, opened_at=opened_at, opened_via=opened_via
            )
            self.session.add(row)
            await self.session.flush()
            return _to_opening(row)
        finally:
            await self.session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY},
            )


@dataclass(slots=True)
class PostgresTokenDirectory:
    """Token resolution, across every organisation."""

    session: AsyncSession

    async def resolve_token(self, token_hash: str, *, now: datetime) -> TokenResolution | None:
        """Return what ``token_hash`` identifies, or ``None``.

        One query, joining the token to its user, because the alternative — read
        the token, then read the user — is two round trips on the hot path of
        every authenticated request.
        """
        row = (
            await self.session.execute(
                select(models.ApiToken, models.User)
                .join(
                    models.User,
                    (models.User.org_id == models.ApiToken.org_id)
                    & (models.User.user_id == models.ApiToken.user_id),
                )
                .where(models.ApiToken.token_hash == token_hash)
            )
        ).first()

        if row is None:
            return None

        token, user = row
        # Unknown, revoked, expired, and belonging to a deactivated user all
        # return ``None``. Distinguishing them would tell an attacker which of
        # their guesses was a real token.
        if token.revoked_at is not None or not user.is_active:
            return None
        expires_at = as_utc(token.expires_at)
        if expires_at is not None and expires_at <= now:
            return None

        return TokenResolution(
            user_id=token.user_id,
            org_id=token.org_id,
            token_id=token.token_id,
            team_node_id=token.team_node_id,
            scopes=as_tuple(token.scopes),
        )

    async def find_token_by_hash(self, token_hash: str) -> TokenLocation | None:
        """Return where ``token_hash`` lives, ignoring whether it is usable."""
        row = (
            await self.session.scalars(
                select(models.ApiToken).where(models.ApiToken.token_hash == token_hash)
            )
        ).first()
        if row is None:
            return None
        return TokenLocation(org_id=row.org_id, token=_to_token(row))


__all__ = ["PostgresIdentityRepository", "PostgresTokenDirectory"]
