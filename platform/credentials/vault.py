"""Encrypted, versioned credential storage — and no way to read one back.

This is the operator's half of Article IV. Everything that puts a credential
into NinjaSRE goes through here: the console, the CLI, the onboarding flow, a
rotation script. Everything that *uses* one goes through the proxy, which is a
different module with a different import, and the difference is the trust
boundary.

**There is no ``reveal`` on this class, and there never will be.** FR-003 says a
credential value must not be returned to any caller outside the proxy, and the
way to make that true is not a check — it is the absence of a method. A reviewer
asking "can this code see credentials?" reads the class surface and is done.
``tools/check_direct_credentials.py`` holds the same line one layer down, by
failing the build on a ``reveal`` call outside ``proxy/``.

**Rotation writes; it does not overwrite.** Each version is its own row —
``datadog/payments@v1``, ``@v2``, ``@v3`` — and a small pointer row at
``datadog/payments`` records which one is live, in its *metadata* labels. Two
consequences follow, and both are the reason for the shape:

- Rotation is non-destructive, so a key that turns out to be wrong is one
  pointer move from being replaced by the one that worked (FR-002). Rolling back
  does not require the operator to still have the old value in a password
  manager somewhere.
- The pointer is metadata, so *reading which version is live never touches a
  value*. Health checks, the console, and the operator CLI all answer "is this
  configured, and since when" without any of them being on the credential path.

The encryption is the store's business, not this module's: ``CredentialStore``
seals on the way in with the operator's key. What the vault adds is the schema
check in front of it (FR-005) and the version bookkeeping around it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from config.constants.security import (
    VAULT_ACTIVE_VERSION_LABEL_PREFIX,
    VAULT_INITIAL_CREDENTIAL_VERSION,
)
from platform.credentials.errors import (
    CredentialNotConfigured,
    CredentialVersionNotFound,
)
from platform.credentials.handles import CredentialHandle, version_of
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import (
    CredentialMetadata,
    CredentialStore,
    PersistenceGateway,
    SecretValue,
    TenantScope,
)


def encode_payload(values: Mapping[str, str]) -> str:
    """Return the stored form of a multi-field credential.

    JSON with sorted keys, so the same credential encodes to the same bytes
    twice. That is not aesthetic: an envelope whose plaintext varies with
    dictionary ordering would make "did this rotation change anything" an
    unanswerable question.
    """
    return json.dumps(dict(sorted(values.items())), separators=(",", ":"))


def decode_payload(payload: str) -> dict[str, str]:
    """Return the fields a stored payload holds.

    Called from the proxy's resolver and from nowhere else. It is here rather
    than beside its caller because it is the inverse of ``encode_payload`` and
    the two have to change together; the boundary that matters is ``reveal``,
    which returns the ciphertext's plaintext, not this, which reshapes a string
    somebody already has.
    """
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("a stored credential payload must be a JSON object of fields")
    return {str(name): str(value) for name, value in decoded.items()}


def active_version_label(version: int) -> str:
    """Return the metadata label that marks ``version`` as the live one."""
    return f"{VAULT_ACTIVE_VERSION_LABEL_PREFIX}{version}"


def active_version_from(metadata: CredentialMetadata) -> int | None:
    """Return the live version a pointer row's labels name, or ``None``."""
    for label in metadata.labels:
        if label.startswith(VAULT_ACTIVE_VERSION_LABEL_PREFIX):
            suffix = label.removeprefix(VAULT_ACTIVE_VERSION_LABEL_PREFIX)
            if suffix.isdigit():
                return int(suffix)
    return None


async def stored_versions(
    credentials: CredentialStore,
    handle: CredentialHandle,
) -> tuple[int, ...]:
    """Return the version numbers stored for ``handle``, unordered.

    A module function rather than a method because the proxy's resolver needs
    the same lookup inside a unit of work it already holds, and a ``Vault``
    method that opened its own would nest a transaction inside a transaction.
    """
    stored = await credentials.list_metadata(integration=handle.integration)
    prefix = handle.qualified
    found: list[int] = []
    for metadata in stored:
        version = version_of(metadata.handle)
        if version is not None and CredentialHandle.parse(metadata.handle).qualified == prefix:
            found.append(version)
    return tuple(found)


async def active_version(
    credentials: CredentialStore,
    handle: CredentialHandle,
) -> CredentialVersion | None:
    """Return the live version of ``handle``, or ``None`` when none is configured."""
    pointer = await credentials.get_metadata(handle.qualified)
    if pointer is None:
        return None
    version = active_version_from(pointer)
    if version is None:
        return None
    metadata = await credentials.get_metadata(handle.version_handle(version))
    if metadata is None:
        raise CredentialVersionNotFound(handle.qualified, version)
    return _version_from(handle, metadata, active=True)


@dataclass(frozen=True, slots=True)
class CredentialVersion:
    """One stored version of a credential, described without being read.

    Everything an operator, a console, or a health check needs — that it exists,
    which version is live, when it was rotated, when it expires — and no field
    that could hold the value. The type is the guarantee: there is no attribute
    to accidentally log.
    """

    handle: CredentialHandle
    version: int
    is_active: bool
    integration: str
    description: str = ""
    created_at: datetime | None = None
    rotated_at: datetime | None = None
    expires_at: datetime | None = None
    key_version: int = 1

    @property
    def stored_handle(self) -> str:
        """Return the handle this version is stored under."""
        return self.handle.version_handle(self.version)

    def is_expired(self, now: datetime) -> bool:
        """Return whether this version's own expiry has passed."""
        return self.expires_at is not None and self.expires_at <= now


class Vault:
    """Encrypted credential storage, scoped to one organisation per call.

    Holds a gateway rather than a unit of work: every method here is a complete
    operation an operator asked for, and each opens its own transaction so that
    a rotation either lands with its pointer move or does not land at all.
    """

    __slots__ = ("_gateway", "_schemas")

    def __init__(self, *, gateway: PersistenceGateway, schemas: CredentialSchemaRegistry) -> None:
        self._gateway = gateway
        self._schemas = schemas

    async def store(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
        values: Mapping[str, str],
        *,
        description: str = "",
        expires_at: datetime | None = None,
    ) -> CredentialVersion:
        """Validate ``values``, store them as a new version, and make it live.

        Raises ``CredentialSchemaViolation`` when the credential does not fit
        the integration's schema (FR-005), and ``UnknownIntegration`` when no
        schema is declared for it. Returns the metadata of the version written —
        never the values.
        """
        self._schemas.get(handle.integration).validate(values)

        async with self._gateway.begin(scope) as uow:
            return await self._append_version(
                uow.credentials,
                handle,
                values,
                description=description,
                expires_at=expires_at,
            )

    async def rotate(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
        values: Mapping[str, str],
        *,
        expires_at: datetime | None = None,
    ) -> CredentialVersion:
        """Store ``values`` as the next version of an existing credential.

        Distinct from ``store`` so the audit trail can tell onboarding an
        integration from responding to a leak, and so rotating something that
        was never configured is an error rather than a silent create. The new
        version becomes live on write, which is what makes SC-004 — rotation
        takes effect on the next request, with no restart — a property of the
        storage rather than of a cache somebody has to remember to invalidate.
        """
        self._schemas.get(handle.integration).validate(values)

        async with self._gateway.begin(scope) as uow:
            existing = await stored_versions(uow.credentials, handle)
            if not existing:
                raise CredentialNotConfigured(handle.qualified, integration=handle.integration)
            previous = await uow.credentials.get_metadata(handle.version_handle(max(existing)))
            return await self._append_version(
                uow.credentials,
                handle,
                values,
                description=previous.description if previous is not None else "",
                expires_at=expires_at,
            )

    async def activate(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
        version: int,
    ) -> CredentialVersion:
        """Make ``version`` the one the proxy resolves, and return it (FR-002).

        This is rollback. It moves a label and touches no value, which is why an
        operator can undo a bad rotation without possessing the credential they
        are rolling back to.
        """
        async with self._gateway.begin(scope) as uow:
            metadata = await uow.credentials.get_metadata(handle.version_handle(version))
            if metadata is None:
                raise CredentialVersionNotFound(handle.qualified, version)
            await self._write_pointer(
                uow.credentials, handle, version, description=metadata.description
            )

        return _version_from(handle, metadata, active=True)

    async def active(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
    ) -> CredentialVersion | None:
        """Return the live version's metadata, or ``None`` when none is configured."""
        async with self._gateway.begin(scope) as uow:
            return await active_version(uow.credentials, handle)

    async def versions(
        self,
        scope: TenantScope,
        handle: CredentialHandle,
    ) -> tuple[CredentialVersion, ...]:
        """Return every stored version of ``handle``, oldest first."""
        async with self._gateway.begin(scope) as uow:
            pointer = await uow.credentials.get_metadata(handle.qualified)
            live = None if pointer is None else active_version_from(pointer)
            found: list[CredentialVersion] = []
            for version in sorted(await stored_versions(uow.credentials, handle)):
                metadata = await uow.credentials.get_metadata(handle.version_handle(version))
                if metadata is not None:
                    found.append(_version_from(handle, metadata, active=version == live))
        return tuple(found)

    async def list(
        self,
        scope: TenantScope,
        *,
        integration: str | None = None,
    ) -> tuple[CredentialVersion, ...]:
        """Return the live version of every configured credential, by handle.

        The metadata-only read API FR-003 asks for. A console renders this; a
        health check reads it; neither is on the credential path.
        """
        async with self._gateway.begin(scope) as uow:
            stored = await uow.credentials.list_metadata(integration=integration)
            handles = sorted(
                {
                    CredentialHandle.parse(metadata.handle)
                    for metadata in stored
                    if version_of(metadata.handle) is not None
                },
                key=lambda handle: handle.qualified,
            )
            found = [await active_version(uow.credentials, handle) for handle in handles]
        return tuple(version for version in found if version is not None)

    async def delete(self, scope: TenantScope, handle: CredentialHandle) -> int:
        """Delete every version of ``handle`` and its pointer, and return how many."""
        async with self._gateway.begin(scope) as uow:
            versions = await stored_versions(uow.credentials, handle)
            for version in versions:
                await uow.credentials.delete(handle.version_handle(version))
            await uow.credentials.delete(handle.qualified)
        return len(versions)

    async def undecryptable(self, scope: TenantScope) -> tuple[str, ...]:
        """Return the handles the configured key cannot open.

        Empty means every stored credential is readable. ``health.py`` calls
        this at startup so a key that did not survive a restore surfaces then.
        """
        async with self._gateway.begin(scope) as uow:
            return await uow.credentials.verify_decryptable()

    # -- writing a version ----------------------------------------------------

    async def _append_version(
        self,
        credentials: CredentialStore,
        handle: CredentialHandle,
        values: Mapping[str, str],
        *,
        description: str,
        expires_at: datetime | None,
    ) -> CredentialVersion:
        """Write the next version of ``handle`` and point at it, in one transaction."""
        versions = await stored_versions(credentials, handle)
        version = max(versions, default=VAULT_INITIAL_CREDENTIAL_VERSION - 1) + 1
        now = datetime.now(UTC)

        stored = await credentials.store(
            CredentialMetadata(
                handle=handle.version_handle(version),
                integration=handle.integration,
                description=description,
                created_at=now,
                rotated_at=now if version > VAULT_INITIAL_CREDENTIAL_VERSION else None,
                expires_at=expires_at,
            ),
            SecretValue(encode_payload(values)),
        )
        await self._write_pointer(credentials, handle, version, description=description)
        return _version_from(handle, stored, active=True)

    # -- the pointer row ------------------------------------------------------

    async def _write_pointer(
        self,
        credentials: CredentialStore,
        handle: CredentialHandle,
        version: int,
        *,
        description: str,
    ) -> None:
        """Record ``version`` as the live one, in metadata a reader may see.

        The pointer's payload repeats the version number rather than being
        empty. A zero-length secret would be a legitimate-looking row that no
        decryption failure could ever be detected on, and ``verify_decryptable``
        is the check that catches a wrong key at boot.
        """
        existing = await credentials.get_metadata(handle.qualified)
        await credentials.store(
            CredentialMetadata(
                handle=handle.qualified,
                integration=handle.integration,
                description=description,
                created_at=existing.created_at if existing is not None else None,
                rotated_at=datetime.now(UTC) if existing is not None else None,
                labels=(active_version_label(version),),
            ),
            SecretValue(encode_payload({"active_version": str(version)})),
        )


def _version_from(
    handle: CredentialHandle,
    metadata: CredentialMetadata,
    *,
    active: bool,
) -> CredentialVersion:
    """Return the value-free description of one stored version."""
    version = version_of(metadata.handle)
    if version is None:
        raise RecordNotFound(kind="credential version", identifier=metadata.handle)
    return CredentialVersion(
        handle=handle,
        version=version,
        is_active=active,
        integration=metadata.integration,
        description=metadata.description,
        created_at=metadata.created_at,
        rotated_at=metadata.rotated_at,
        expires_at=metadata.expires_at,
        key_version=metadata.key_version,
    )


__all__ = [
    "CredentialVersion",
    "Vault",
    "active_version_from",
    "active_version_label",
    "decode_payload",
    "encode_payload",
]
