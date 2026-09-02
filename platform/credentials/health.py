"""Which integrations are usable, answered without revealing anything (FR-020).

An operator's real question is "will this work when the alert fires", and there
are exactly three ways it will not: nothing is configured, what is configured has
expired, or what is configured cannot be decrypted with the key this process
holds. Those need different actions — add a credential, rotate it, restore the
key — so they are three states rather than one boolean.

Every read here goes through the vault's metadata API. Nothing in this module
touches a value, which is what lets a health endpoint be exposed to a console
without it becoming a credential-reading path.

The startup check is the one with teeth. A deployment that boots with the wrong
encryption key works perfectly until the first credential is needed, and the
first credential is needed during an incident. ``verify_startup`` fails the boot
instead, naming the handles, so the failure lands on somebody who is already
looking at a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from platform.credentials.errors import VaultKeyMismatch
from platform.credentials.handles import CredentialHandle
from platform.credentials.vault import CredentialVersion, Vault
from platform.persistence.ports import TenantScope


class CredentialHealthState(StrEnum):
    """Whether an integration's credential will work, and if not, why not."""

    CONFIGURED = "configured"
    MISSING = "missing"
    EXPIRED = "expired"
    UNDECRYPTABLE = "undecryptable"

    @property
    def usable(self) -> bool:
        """Return whether a call using this credential could succeed right now."""
        return self is CredentialHealthState.CONFIGURED


@dataclass(frozen=True, slots=True)
class IntegrationCredentialHealth:
    """One integration's credential, described without being read."""

    integration: str
    handle: str
    state: CredentialHealthState
    version: int | None = None
    rotated_at: datetime | None = None
    expires_at: datetime | None = None

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "integration": self.integration,
            "handle": self.handle,
            "state": str(self.state),
            "version": self.version,
            "rotated_at": None if self.rotated_at is None else self.rotated_at.isoformat(),
            "expires_at": None if self.expires_at is None else self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CredentialHealthReport:
    """Every declared integration's credential state, for one tenant."""

    entries: tuple[IntegrationCredentialHealth, ...]
    undecryptable_handles: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        """Return whether every declared integration has a usable credential."""
        return all(entry.state.usable for entry in self.entries)

    @property
    def unusable(self) -> tuple[IntegrationCredentialHealth, ...]:
        """Return the entries an operator has to act on, in name order."""
        return tuple(entry for entry in self.entries if not entry.state.usable)

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "healthy": self.healthy,
            "integrations": [entry.to_record() for entry in self.entries],
            "undecryptable": list(self.undecryptable_handles),
        }


class CredentialHealth:
    """Reports per-integration credential state for one tenant.

    Takes the list of integrations to check rather than discovering it, because
    "which integrations should this deployment have" is a configuration question
    and answering it from what happens to be stored would report a healthy
    deployment that is missing half its catalogue.
    """

    __slots__ = ("_vault",)

    def __init__(self, *, vault: Vault) -> None:
        self._vault = vault

    async def report(
        self,
        scope: TenantScope,
        *,
        integrations: tuple[str, ...],
        team_id: str,
        now: datetime | None = None,
    ) -> CredentialHealthReport:
        """Return the state of each of ``integrations`` for ``team_id``."""
        at = now if now is not None else datetime.now(UTC)
        undecryptable = await self._vault.undecryptable(scope)
        unreadable = set(undecryptable)
        # Two reads for any number of integrations: the live versions, all at
        # once, and the handles that do not decrypt. Asking the vault for
        # each integration's version in turn — and again for its fallback —
        # was two transactions per vendor on a screen that lists them all.
        live = {version.handle.qualified: version for version in await self._vault.list(scope)}

        entries: list[IntegrationCredentialHealth] = []
        for integration in sorted(integrations):
            handle = CredentialHandle(integration=integration, team_id=team_id)
            entries.append(_entry(handle, live=live, unreadable=unreadable, now=at))
        return CredentialHealthReport(
            entries=tuple(entries), undecryptable_handles=tuple(sorted(undecryptable))
        )


def _entry(
    handle: CredentialHandle,
    *,
    live: dict[str, CredentialVersion],
    unreadable: set[str],
    now: datetime,
) -> IntegrationCredentialHealth:
    """Return one integration's health, following the same fallback the proxy does."""
    version = live.get(handle.qualified)
    resolved_handle = handle
    if version is None:
        fallback = handle.fallback()
        if fallback is not None:
            version = live.get(fallback.qualified)
            resolved_handle = fallback

    if version is None:
        return IntegrationCredentialHealth(
            integration=handle.integration,
            handle=handle.qualified,
            state=CredentialHealthState.MISSING,
        )

    state = CredentialHealthState.CONFIGURED
    if version.stored_handle in unreadable:
        state = CredentialHealthState.UNDECRYPTABLE
    elif version.is_expired(now):
        state = CredentialHealthState.EXPIRED

    return IntegrationCredentialHealth(
        integration=handle.integration,
        handle=resolved_handle.qualified,
        state=state,
        version=version.version,
        rotated_at=version.rotated_at,
        expires_at=version.expires_at,
    )


async def verify_startup(vault: Vault, scope: TenantScope) -> None:
    """Raise ``VaultKeyMismatch`` if any stored credential cannot be decrypted.

    Called at boot. A key that did not survive a restore is the failure this
    catches, and catching it here rather than at first use is the difference
    between a deployment that refuses to start and one that fails halfway
    through an incident.
    """
    handles = await vault.undecryptable(scope)
    if handles:
        raise VaultKeyMismatch(handles)


__all__ = [
    "CredentialHealth",
    "CredentialHealthReport",
    "CredentialHealthState",
    "IntegrationCredentialHealth",
    "verify_startup",
]
