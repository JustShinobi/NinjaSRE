"""In-memory users, token hashes, and role bindings."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.errors import DuplicateRecord, RecordNotFound
from platform.persistence.fakes.state import State, TenantState
from platform.persistence.ports.identity_repository import (
    ApiToken,
    RoleBinding,
    TokenResolution,
    User,
)


@dataclass(slots=True)
class FakeIdentityRepository:
    """Users, tokens, and role bindings for one organisation."""

    org_id: str
    state: TenantState

    async def get_user(self, user_id: str) -> User | None:
        """Return the user with ``user_id``, or ``None``."""
        return self.state.users.get(user_id)

    async def find_user_by_email(self, email: str) -> User | None:
        """Return the user with ``email``, or ``None``."""
        wanted = email.casefold()
        return next((u for u in self.state.users.values() if u.email.casefold() == wanted), None)

    async def find_user_by_subject(self, external_subject: str) -> User | None:
        """Return the user bound to an SSO subject identifier, or ``None``."""
        return next(
            (u for u in self.state.users.values() if u.external_subject == external_subject),
            None,
        )

    async def upsert_user(self, user: User) -> User:
        """Store ``user`` and return it as stored."""
        stored = user if user.created_at is not None else replace(user, created_at=_now())
        self.state.users[user.user_id] = stored
        return stored

    async def list_users(self) -> tuple[User, ...]:
        """Return every user in this tenant, ordered by email."""
        return tuple(sorted(self.state.users.values(), key=lambda u: (u.email, u.user_id)))

    async def store_token(self, token: ApiToken) -> ApiToken:
        """Store ``token`` by hash and return it."""
        self._require_user(token.user_id)
        if token.token_id in self.state.tokens:
            raise DuplicateRecord(kind="api token", identifier=token.token_id)
        clash = next(
            (t for t in self.state.tokens.values() if t.token_hash == token.token_hash),
            None,
        )
        if clash is not None:
            raise DuplicateRecord(kind="api token hash", identifier=clash.token_id)

        stored = token if token.created_at is not None else replace(token, created_at=_now())
        self.state.tokens[token.token_id] = stored
        return stored

    async def revoke_token(self, token_id: str, *, revoked_at: datetime) -> bool:
        """Mark ``token_id`` revoked and return whether it existed and was live."""
        token = self.state.tokens.get(token_id)
        if token is None or token.is_revoked:
            return False
        self.state.tokens[token_id] = replace(token, revoked_at=revoked_at)
        return True

    async def tokens_for_user(self, user_id: str) -> tuple[ApiToken, ...]:
        """Return the user's tokens, newest first, revoked ones included."""
        owned = [t for t in self.state.tokens.values() if t.user_id == user_id]
        return tuple(sorted(owned, key=_token_order, reverse=True))

    async def upsert_role_binding(self, binding: RoleBinding) -> RoleBinding:
        """Store ``binding`` and return it as stored."""
        self._require_user(binding.user_id)
        stored = binding if binding.granted_at is not None else replace(binding, granted_at=_now())
        self.state.role_bindings[binding.binding_id] = stored
        return stored

    async def role_bindings_for_user(self, user_id: str) -> tuple[RoleBinding, ...]:
        """Return every role binding held by ``user_id``."""
        held = [b for b in self.state.role_bindings.values() if b.user_id == user_id]
        return tuple(sorted(held, key=lambda b: (b.role, b.binding_id)))

    async def remove_role_binding(self, binding_id: str) -> bool:
        """Remove ``binding_id`` and return whether it existed."""
        return self.state.role_bindings.pop(binding_id, None) is not None

    def _require_user(self, user_id: str) -> None:
        """Raise unless ``user_id`` exists in this tenant.

        The Postgres schema enforces this with a composite foreign key. The
        fake has to enforce it too, or a feature developed against the fake
        would write a token for a user who does not exist and only find out in
        production — which is exactly the divergence running one contract suite
        against both backends exists to catch. It caught this one.
        """
        if user_id not in self.state.users:
            raise RecordNotFound(kind="user", identifier=user_id)


@dataclass(slots=True)
class FakeTokenDirectory:
    """Token resolution, across every organisation."""

    state: State

    async def resolve_token(self, token_hash: str, *, now: datetime) -> TokenResolution | None:
        """Return what ``token_hash`` identifies, or ``None``."""
        for org_id, tenant in self.state.tenants.items():
            for token in tenant.tokens.values():
                if token.token_hash != token_hash:
                    continue
                if token.is_revoked:
                    return None
                if token.expires_at is not None and token.expires_at <= now:
                    return None
                user = tenant.users.get(token.user_id)
                if user is None or not user.is_active:
                    return None
                return TokenResolution(
                    user_id=token.user_id,
                    org_id=org_id,
                    token_id=token.token_id,
                    scopes=token.scopes,
                )
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _token_order(token: ApiToken) -> tuple[datetime, str]:
    """Order tokens by creation, with the id breaking ties deterministically."""
    return (token.created_at or datetime.min.replace(tzinfo=UTC), token.token_id)


__all__ = ["FakeIdentityRepository", "FakeTokenDirectory"]
