"""Credentials, encrypted at rest and reachable by exactly one caller.

Article IV says no credential reaches the agent — not in an environment
variable, a prompt, a tool argument, the filesystem, or a trace. This port is
the storage half of that, and it holds the line in three places.

**Secret material is wrapped.** ``SecretValue`` is the only type here that
carries a plaintext, and it refuses to render itself: its ``repr`` and ``str``
are both a placeholder, so a secret cannot reach a log line, an f-string, a
structlog field, or a traceback by accident. Getting the value out takes a call
to ``reveal``, which is greppable — and the grep returning exactly the credential
proxy is the audit.

**Metadata and secret are separate types.** Everything that wants to *list*
credentials, check whether one is configured, or show them in a console works
with ``CredentialMetadata``, which has no field that could hold a secret. Only
``reveal`` returns a ``SecretValue``, so "does this code see credentials" is a
question about one method rather than about every read path.

**Errors name handles, never values** (FR-019). ``CredentialUndecryptable``
carries the handle so an operator can find the row; nothing in this package puts
a decrypted value into an exception, a log, or a query echo.

The encryption itself is not this port's business. The implementation encrypts
on the way in with the operator's key (FR-018); the port's contract is that what
goes in comes back out, and that a backend which stored it in plaintext would
fail ``verify_decryptable`` against a rotated key exactly as a correct one does
not.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, final, runtime_checkable

#: What a secret renders as, everywhere a secret might be rendered.
REDACTED = "<redacted>"


@final
class SecretValue:
    """A string that will not print itself.

    Equality is constant-time, because the obvious use of ``==`` on a secret is
    checking a presented credential against a stored one, and the obvious
    implementation of that leaks the length of the matching prefix.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Return the plaintext.

        The only way to get it, and deliberately conspicuous. In first-party
        code this is called by the credential proxy, which injects the value at
        the network edge, and by nothing else.
        """
        return self._value

    def __repr__(self) -> str:
        return f"SecretValue({REDACTED})"

    def __str__(self) -> str:
        return REDACTED

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretValue):
            return NotImplemented
        return hmac.compare_digest(self._value, other._value)

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)


@dataclass(frozen=True, slots=True)
class CredentialMetadata:
    """Everything about a credential except the credential.

    ``handle`` is what the rest of the platform passes around. A capability
    declares that it needs the credential behind a handle; the proxy resolves
    it; the agent sees the handle and never the value.
    """

    handle: str
    integration: str
    key_version: int = 1
    description: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    rotated_at: datetime | None = None
    expires_at: datetime | None = None
    labels: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class CredentialStore(Protocol):
    """Encrypted credential storage, within one tenant."""

    async def store(
        self,
        metadata: CredentialMetadata,
        secret: SecretValue,
    ) -> CredentialMetadata:
        """Encrypt and store ``secret`` under ``metadata.handle``, and return the metadata.

        Returns metadata rather than nothing so the caller has the stored
        ``key_version`` and timestamps without a second read — and so that the
        obvious thing to log after a store is a value with no secret in it.
        """

    async def get_metadata(self, handle: str) -> CredentialMetadata | None:
        """Return what is known about ``handle`` except its value, or ``None``."""

    async def list_metadata(
        self,
        *,
        integration: str | None = None,
    ) -> tuple[CredentialMetadata, ...]:
        """Return metadata for this tenant's credentials, ordered by handle."""

    async def reveal(self, handle: str) -> SecretValue:
        """Decrypt and return the credential behind ``handle``.

        **The credential proxy calls this. Nothing else does.** Every other
        caller wants ``get_metadata``, and a change that puts a second caller
        here is a change to the trust boundary, not a convenience.

        Raises ``RecordNotFound`` for an unknown handle and
        ``CredentialUndecryptable`` when the configured key is not the one that
        wrote the row.
        """

    async def rotate(
        self,
        handle: str,
        secret: SecretValue,
        *,
        key_version: int,
        rotated_at: datetime,
    ) -> CredentialMetadata:
        """Replace the stored secret and return the updated metadata.

        Raises ``RecordNotFound`` for an unknown handle. Rotation is a distinct
        operation from ``store`` so that the audit trail can tell a new
        credential from a replaced one — which is the difference between
        onboarding an integration and responding to a leak.
        """

    async def delete(self, handle: str) -> bool:
        """Delete the credential and return whether it existed."""

    async def verify_decryptable(self) -> tuple[str, ...]:
        """Return the handles that cannot be decrypted with the configured key.

        Empty means every stored credential is readable. The health check calls
        this at start so a key that did not survive a restore surfaces then,
        rather than during the first incident that needs the one integration
        nobody tested.
        """


__all__ = [
    "REDACTED",
    "CredentialMetadata",
    "CredentialStore",
    "SecretValue",
]
