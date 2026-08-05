"""Encrypted credentials over PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select, text
from sqlalchemy.orm import defer

from platform.persistence.errors import CredentialUndecryptable, RecordNotFound
from platform.persistence.ports.credential_store import CredentialMetadata, SecretValue
from platform.persistence.postgres import models
from platform.persistence.postgres.crypto import unseal
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    utc_now,
)


def _to_metadata(row: models.Credential) -> CredentialMetadata:
    return CredentialMetadata(
        handle=row.handle,
        integration=row.integration,
        key_version=row.key_version,
        description=row.description,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
        rotated_at=as_utc(row.rotated_at),
        expires_at=as_utc(row.expires_at),
        labels=as_tuple(row.labels),
    )


@dataclass(slots=True)
class PostgresCredentialStore(TenantBound):
    """Credentials for one organisation, encrypted at rest (FR-018).

    Every read path but ``reveal`` defers the secret column, so a listing never
    decrypts. That is not an optimisation. It means a deployment whose key is
    wrong can still show an operator what is configured — and that a bug in a
    listing cannot leak a value it never fetched.
    """

    async def store(
        self,
        metadata: CredentialMetadata,
        secret: SecretValue,
    ) -> CredentialMetadata:
        """Encrypt and store ``secret`` under ``metadata.handle``, and return the metadata."""
        stamped = utc_now()
        row = await self.session.get(
            models.Credential,
            (self.org_id, metadata.handle),
            options=[defer(models.Credential.secret)],
        )
        if row is None:
            row = models.Credential(org_id=self.org_id, handle=metadata.handle)
            self.session.add(row)
            row.created_at = metadata.created_at or stamped

        row.integration = metadata.integration
        # Assigned as plaintext; the ``EncryptedSecret`` column type seals it on
        # the way to the database, so what the table holds is an AES-GCM
        # envelope and nothing else.
        row.secret = secret.reveal()
        row.key_version = metadata.key_version
        row.description = metadata.description
        row.labels = as_list(metadata.labels)
        row.updated_at = stamped
        row.rotated_at = metadata.rotated_at
        row.expires_at = metadata.expires_at

        await self.session.flush()
        return _to_metadata(row)

    async def get_metadata(self, handle: str) -> CredentialMetadata | None:
        """Return what is known about ``handle`` except its value, or ``None``."""
        row = await self.session.scalar(
            self._metadata_query().where(models.Credential.handle == handle)
        )
        return _to_metadata(row) if row is not None else None

    async def list_metadata(
        self,
        *,
        integration: str | None = None,
    ) -> tuple[CredentialMetadata, ...]:
        """Return metadata for this tenant's credentials, ordered by handle."""
        statement = self._metadata_query().order_by(models.Credential.handle)
        if integration is not None:
            statement = statement.where(models.Credential.integration == integration)
        rows = await self.session.scalars(statement)
        return tuple(_to_metadata(row) for row in rows)

    async def reveal(self, handle: str) -> SecretValue:
        """Decrypt and return the credential behind ``handle``.

        **The credential proxy calls this. Nothing else does.** It is the one
        method in this package that returns secret material, which is what makes
        "does this code see credentials" a question about a single call site.
        """
        envelope = await self.session.scalar(
            text("SELECT secret FROM credentials WHERE org_id = :org_id AND handle = :handle"),
            {"org_id": self.org_id, "handle": handle},
        )
        if envelope is None:
            raise RecordNotFound(kind="credential", identifier=handle)
        try:
            return SecretValue(unseal(envelope))
        except Exception as error:
            # Anything at all going wrong while opening a stored value means it
            # cannot be relied on. The handle is what an operator needs; the
            # value, the key, and the ciphertext are what an attacker would.
            raise CredentialUndecryptable(handle) from error

    async def rotate(
        self,
        handle: str,
        secret: SecretValue,
        *,
        key_version: int,
        rotated_at: datetime,
    ) -> CredentialMetadata:
        """Replace the stored secret and return the updated metadata."""
        row = await self.session.get(
            models.Credential,
            (self.org_id, handle),
            options=[defer(models.Credential.secret)],
        )
        if row is None:
            raise RecordNotFound(kind="credential", identifier=handle)

        row.secret = secret.reveal()
        row.key_version = key_version
        row.rotated_at = rotated_at
        row.updated_at = rotated_at
        await self.session.flush()
        return _to_metadata(row)

    async def delete(self, handle: str) -> bool:
        """Delete the credential and return whether it existed."""
        row = await self.session.get(
            models.Credential,
            (self.org_id, handle),
            options=[defer(models.Credential.secret)],
        )
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def verify_decryptable(self) -> tuple[str, ...]:
        """Return the handles that cannot be decrypted with the configured key.

        Reads the envelopes directly and opens each one by hand rather than
        through the column type, which raises on the first bad row. An operator
        restoring a backup with the wrong key wants to know how much is
        affected, not which credential happened to sort first.
        """
        rows = await self.session.execute(
            text("SELECT handle, secret FROM credentials WHERE org_id = :org_id"),
            {"org_id": self.org_id},
        )

        failed: list[str] = []
        for handle, envelope in rows.all():
            try:
                unseal(envelope)
            except Exception:  # noqa: BLE001 — any failure means "not readable"
                failed.append(handle)
        return tuple(sorted(failed))

    def _metadata_query(self) -> Select[tuple[models.Credential]]:
        """Return a query over this tenant's credentials that does not load the secret."""
        return (
            select(models.Credential)
            .where(models.Credential.org_id == self.org_id)
            .options(defer(models.Credential.secret))
        )


__all__ = ["PostgresCredentialStore"]
