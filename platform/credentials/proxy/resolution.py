"""Handle plus tenant plus team, to a credential. The one place that reads one.

**This module is the only first-party caller of ``CredentialStore.reveal``.**
That is not a convention; ``tools/check_direct_credentials.py`` fails the build
on a ``reveal`` call anywhere else, and the reason the rule can be that blunt is
that everything else in NinjaSRE genuinely wants metadata. A second caller here
would be a change to the trust boundary, and making it a build failure means it
gets discussed rather than merged.

Resolution is FR-007: a request carries a tenant, a team, and an integration,
and exactly one credential comes back. Two properties of how it does that are
worth stating.

**Scope comes from the caller's identity, not from the request body.** The unit
of work is opened for the organisation on the request, and every repository it
hands out is bound to that organisation — so SC-007, two teams that never
cross-resolve, is satisfied by there being no way to phrase the cross-tenant
read, not by a check that could be removed.

**Team narrows, the organisation backs it up.** A team with its own credential
uses it; a team without one uses the organisation's. Exactly one step of
fallback, and the version that answered is recorded, so "which credential did
this call use" has a recorded answer rather than a computed one.

The plaintext lives in a ``ResolvedCredential`` for the width of one request. It
is not cached. A cache here would be the thing that makes SC-004 — rotation
takes effect on the next request — false, and it would keep secrets in memory
between calls for a saving the vendor's own latency swamps.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from platform.credentials.errors import CredentialNotConfigured
from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault, active_version, decode_payload
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import PersistenceGateway, TenantScope


@dataclass(frozen=True, slots=True)
class ResolvedCredential:
    """One credential, resolved, for the duration of one request.

    Holds plaintext, so it is the one type in this package that must not be
    logged, returned above the proxy, or put in an audit record. Everything that
    wants to *describe* a credential uses ``CredentialVersion``, which cannot
    hold a value at all.

    ``__repr__`` is overridden anyway. Belt and braces: a dataclass repr reaches
    tracebacks and pytest failure output, and a secret only has to escape once.
    """

    handle: CredentialHandle
    version: int
    values: Mapping[str, str] = field(repr=False)
    expires_at: datetime | None = None

    def __repr__(self) -> str:
        return (
            f"ResolvedCredential(handle={self.handle.qualified!r}, "
            f"version={self.version}, fields={sorted(self.values)})"
        )

    def __str__(self) -> str:
        return repr(self)

    def with_values(
        self,
        values: Mapping[str, str],
        *,
        expires_at: datetime | None,
    ) -> ResolvedCredential:
        """Return a copy carrying refreshed values and a new expiry."""
        return replace(self, values=dict(values), expires_at=expires_at)

    def is_expired(self, now: datetime) -> bool:
        """Return whether this credential's expiry has already passed."""
        return self.expires_at is not None and self.expires_at <= now


class CredentialResolver:
    """Turns a tenant, a team, and an integration into a usable credential.

    Holds a gateway and opens one unit of work per resolution. That is a read
    per proxied request, which is what makes rotation take effect immediately —
    and the alternative, a cache with an invalidation story, is how a rotated
    credential keeps working for the fifteen minutes nobody budgeted for.
    """

    __slots__ = ("_gateway", "_schemas", "_vault")

    def __init__(self, *, gateway: PersistenceGateway, schemas: CredentialSchemaRegistry) -> None:
        self._gateway = gateway
        self._schemas = schemas
        self._vault = Vault(gateway=gateway, schemas=schemas)

    @property
    def vault(self) -> Vault:
        """Return the vault this resolver reads through, for health and listing."""
        return self._vault

    async def resolve(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
    ) -> ResolvedCredential:
        """Return the credential behind ``handle``, falling back to the organisation's.

        Raises ``CredentialNotConfigured`` when neither the team nor the
        organisation has one, and ``CredentialUndecryptable`` when a row exists
        that the configured key cannot open — a distinction that matters,
        because the first is an operator action and the second is a key
        restore.
        """
        candidates = [handle]
        fallback = handle.fallback()
        if fallback is not None:
            candidates.append(fallback)

        for candidate in candidates:
            resolved = await self._resolve_exact(scope, candidate)
            if resolved is not None:
                return resolved

        raise CredentialNotConfigured(handle.qualified, integration=handle.integration)

    async def _resolve_exact(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
    ) -> ResolvedCredential | None:
        """Return the live version of exactly ``handle``, or ``None`` if there is none.

        Pointer read and value read happen in one unit of work, so a rotation
        landing between them cannot produce a version number that no longer
        matches the row it names.
        """
        async with self._gateway.begin(scope) as uow:
            version = await active_version(uow.credentials, handle)
            if version is None:
                return None
            try:
                secret = await uow.credentials.reveal(version.stored_handle)
            except RecordNotFound:
                return None

            return ResolvedCredential(
                handle=handle,
                version=version.version,
                values=decode_payload(secret.reveal()),
                expires_at=version.expires_at,
            )


__all__ = [
    "CredentialResolver",
    "ResolvedCredential",
]
