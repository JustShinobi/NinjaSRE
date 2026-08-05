"""In-memory credential storage, with the same access shape as the real one."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.errors import RecordNotFound
from platform.persistence.fakes.state import StoredCredential, TenantState
from platform.persistence.ports.credential_store import CredentialMetadata, SecretValue


@dataclass(slots=True)
class FakeCredentialStore:
    """Credentials for one organisation.

    There is no rest to encrypt at, so nothing here is encrypted — FR-018 is a
    property of the Postgres backend and is tested against it. What this fake
    does hold to is the *access* contract, which is the half that constrains
    every caller: metadata reads never return secret material, ``reveal`` is
    the only method that does, and the secret sits inside a ``SecretValue``
    whose ``repr`` is redacted even here.
    """

    org_id: str
    state: TenantState

    async def store(
        self,
        metadata: CredentialMetadata,
        secret: SecretValue,
    ) -> CredentialMetadata:
        """Encrypt and store ``secret`` under ``metadata.handle``, and return the metadata."""
        now = datetime.now(UTC)
        stored_metadata = replace(
            metadata,
            created_at=metadata.created_at or now,
            updated_at=now,
        )
        self.state.credentials[metadata.handle] = StoredCredential(
            metadata=stored_metadata,
            secret=secret,
        )
        return stored_metadata

    async def get_metadata(self, handle: str) -> CredentialMetadata | None:
        """Return what is known about ``handle`` except its value, or ``None``."""
        stored = self.state.credentials.get(handle)
        return stored.metadata if stored is not None else None

    async def list_metadata(
        self,
        *,
        integration: str | None = None,
    ) -> tuple[CredentialMetadata, ...]:
        """Return metadata for this tenant's credentials, ordered by handle."""
        found = [
            stored.metadata
            for stored in self.state.credentials.values()
            if integration is None or stored.metadata.integration == integration
        ]
        return tuple(sorted(found, key=lambda m: m.handle))

    async def reveal(self, handle: str) -> SecretValue:
        """Decrypt and return the credential behind ``handle``."""
        stored = self.state.credentials.get(handle)
        if stored is None:
            raise RecordNotFound(kind="credential", identifier=handle)
        return stored.secret

    async def rotate(
        self,
        handle: str,
        secret: SecretValue,
        *,
        key_version: int,
        rotated_at: datetime,
    ) -> CredentialMetadata:
        """Replace the stored secret and return the updated metadata."""
        stored = self.state.credentials.get(handle)
        if stored is None:
            raise RecordNotFound(kind="credential", identifier=handle)

        metadata = replace(
            stored.metadata,
            key_version=key_version,
            rotated_at=rotated_at,
            updated_at=rotated_at,
        )
        self.state.credentials[handle] = StoredCredential(metadata=metadata, secret=secret)
        return metadata

    async def delete(self, handle: str) -> bool:
        """Delete the credential and return whether it existed."""
        return self.state.credentials.pop(handle, None) is not None

    async def verify_decryptable(self) -> tuple[str, ...]:
        """Return the handles that cannot be decrypted with the configured key.

        Always empty here: there is no key, so there is nothing for one to be
        wrong about. The Postgres backend is where this earns its keep, and the
        contract suite asserts the shape of the answer rather than that it is
        ever non-empty — a fake that could fail decryption would be simulating
        a bug rather than standing in for a store.
        """
        return ()


__all__ = ["FakeCredentialStore"]
