"""Credential columns encrypted at rest, with the key from the operator's config.

FR-018 asks for an encrypted SQLAlchemy column type, and that phrasing decides
the shape of this module. A column type is constructed when the model class is
defined — at import, before any configuration has happened — so it cannot be
handed a key. Something has to hold one.

That something is ``KEY_RING``, and it is the only piece of process-global state
in this package. It is worth the exception because the alternative is worse:
passing a cipher explicitly means every model that grows an encrypted column
needs a constructor argument threaded to it, and the first one that forgets
stores plaintext that looks exactly like ciphertext to every reader.

The guarantees, and what each is worth:

**AES-256-GCM.** Authenticated, so a modified ciphertext fails to decrypt rather
than decrypting to something else. A credential store that could be tampered
into returning an attacker's value would be worse than one with no encryption,
because it would be trusted.

**A random nonce per write.** Stored alongside the ciphertext. Reusing a nonce
under GCM is not a weakness, it is a break — it leaks the XOR of two plaintexts
and eventually the authentication key — so it is generated per encryption and
never derived from the record.

**Failure is loud.** A wrong key raises ``CredentialUndecryptable`` naming the
handle and never the value (FR-019). The health check calls
``verify_decryptable`` at startup, so a key that did not survive a restore
surfaces then rather than during the first incident that needs it.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from config.constants.persistence import (
    DATABASE_ENCRYPTION_KEY_BYTES,
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
)

#: AES-256, under the name this module's callers already use. Shorter keys are
#: refused rather than stretched: a deployment that configured 16 bytes should
#: be told, not quietly given less than it asked for.
KEY_LENGTH_BYTES: Final = DATABASE_ENCRYPTION_KEY_BYTES

#: GCM's standard nonce width. Twelve bytes is what the mode is specified for;
#: other lengths are legal, slower, and buy nothing here.
NONCE_LENGTH_BYTES: Final = 12

#: Version byte, so a future change of cipher can be told from this one by
#: reading a row rather than by remembering when the deployment was created.
ENVELOPE_VERSION: Final = 1


class EncryptionNotConfigured(RuntimeError):
    """A credential was read or written before a key was configured."""

    def __init__(self) -> None:
        super().__init__(
            f"No encryption key is configured. Set {NINJASRE_DATABASE_ENCRYPTION_KEY_ENV} "
            f"to a base64-encoded {KEY_LENGTH_BYTES}-byte key, or call "
            f"KEY_RING.configure() with one."
        )


class UndecryptableValue(ValueError):
    """Stored bytes that this key cannot open.

    Carries nothing but the fact. The credential store catches it and re-raises
    as ``CredentialUndecryptable`` with the handle, because the handle is the
    part an operator needs and the column type does not know it.
    """


@dataclass(frozen=True, slots=True)
class Envelope:
    """One encrypted value, as stored: version, nonce, and ciphertext."""

    version: int
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        """Return the wire form: one version byte, the nonce, then the ciphertext."""
        return bytes([self.version]) + self.nonce + self.ciphertext

    @classmethod
    def from_bytes(cls, raw: bytes) -> Envelope:
        """Return the envelope ``raw`` encodes, or raise ``UndecryptableValue``.

        A column holding something that is not an envelope at all — the result
        of a botched plaintext migration, most likely — is worth telling apart
        from a wrong key, and the exception message says which happened.
        """
        if len(raw) < 1 + NONCE_LENGTH_BYTES + 1:
            raise UndecryptableValue("the stored value is too short to be an encrypted envelope")
        if raw[0] != ENVELOPE_VERSION:
            raise UndecryptableValue(
                f"the stored value declares envelope version {raw[0]}, "
                f"and this release writes version {ENVELOPE_VERSION}"
            )
        return cls(
            version=raw[0],
            nonce=raw[1 : 1 + NONCE_LENGTH_BYTES],
            ciphertext=raw[1 + NONCE_LENGTH_BYTES :],
        )


def decode_key(material: str) -> bytes:
    """Return the raw key ``material`` encodes, or raise ``ValueError``.

    Base64, because a key is bytes and every way of putting bytes in an
    environment variable except an encoding is a way of losing some of them.
    """
    try:
        key = base64.b64decode(material, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("the encryption key is not valid base64") from error
    if len(key) != KEY_LENGTH_BYTES:
        raise ValueError(
            f"the encryption key decodes to {len(key)} bytes; AES-256 needs {KEY_LENGTH_BYTES}"
        )
    return key


def generate_key() -> str:
    """Return a fresh base64-encoded key, for an operator provisioning a deployment."""
    return base64.b64encode(secrets.token_bytes(KEY_LENGTH_BYTES)).decode("ascii")


class KeyRing:
    """Holds the key the encrypted column type encrypts with.

    Configured once at startup, from the operator's environment or explicitly.
    Deliberately a named module-level instance rather than a singleton with
    hidden lookup, so "where does the key come from" has one answer a reader can
    follow to its source.
    """

    __slots__ = ("_key", "_previous")

    def __init__(self) -> None:
        self._key: bytes | None = None
        self._previous: bytes | None = None

    def configure(self, key: bytes) -> None:
        """Install ``key`` as the encryption key."""
        if len(key) != KEY_LENGTH_BYTES:
            raise ValueError(f"an encryption key must be {KEY_LENGTH_BYTES} bytes, got {len(key)}")
        self._key = key

    def configure_previous(self, key: bytes) -> None:
        """Install ``key`` as a read-only fallback, for the duration of a rotation.

        This is what makes key rotation an online operation (FR-021). Writes
        always use the current key; reads try it first and fall back to this
        one, so a row that has not been re-encrypted yet is still readable and
        no request fails while the rotation walks the table.

        It is never used for writing. A fallback that could write would let a
        half-finished rotation go backwards.
        """
        if len(key) != KEY_LENGTH_BYTES:
            raise ValueError(f"an encryption key must be {KEY_LENGTH_BYTES} bytes, got {len(key)}")
        self._previous = key

    def clear_previous(self) -> None:
        """Forget the fallback key, which a rotation does once it has rewritten everything."""
        self._previous = None

    @property
    def has_previous(self) -> bool:
        """Return whether a fallback key is installed."""
        return self._previous is not None

    def configure_from_environment(self) -> bool:
        """Install the key the operator's environment names, and say whether one was there.

        Returns ``False`` rather than raising when the variable is unset. A
        deployment that stores no credentials is legitimate and should not fail
        to start over a key it will never use; the health check reports the
        absence, and the first credential write is where it becomes an error.
        """
        material = os.environ.get(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV)
        if not material:
            return False
        self.configure(decode_key(material))
        return True

    def clear(self) -> None:
        """Forget the configured key, and any fallback."""
        self._key = None
        self._previous = None

    @property
    def is_configured(self) -> bool:
        """Return whether a key is available."""
        return self._key is not None

    def cipher(self) -> AESGCM:
        """Return the cipher used for writing, or raise ``EncryptionNotConfigured``."""
        if self._key is None:
            raise EncryptionNotConfigured
        return AESGCM(self._key)

    def read_ciphers(self) -> tuple[AESGCM, ...]:
        """Return the ciphers a read may try, current key first.

        Ordered rather than a set: during a rotation most rows are under one of
        the two keys and trying the current one first is what keeps the common
        read at one decryption attempt.
        """
        if self._key is None:
            raise EncryptionNotConfigured
        if self._previous is None:
            return (AESGCM(self._key),)
        return (AESGCM(self._key), AESGCM(self._previous))


#: The process's key. One per process, because one database's rows are
#: encrypted with one key.
KEY_RING = KeyRing()


def seal(plaintext: str) -> bytes:
    """Return ``plaintext`` encrypted under the configured key."""
    nonce = secrets.token_bytes(NONCE_LENGTH_BYTES)
    ciphertext = KEY_RING.cipher().encrypt(nonce, plaintext.encode("utf-8"), None)
    return Envelope(version=ENVELOPE_VERSION, nonce=nonce, ciphertext=ciphertext).to_bytes()


def unseal(raw: bytes) -> str:
    """Return the plaintext ``raw`` holds, or raise ``UndecryptableValue``.

    Never puts the value, the key, or the ciphertext in the exception. What a
    caller needs is that this one failed; what an attacker would want is
    everything else.
    """
    envelope = Envelope.from_bytes(raw)
    failure: InvalidTag | None = None
    for cipher in KEY_RING.read_ciphers():
        try:
            plaintext = cipher.decrypt(envelope.nonce, envelope.ciphertext, None)
        except InvalidTag as error:
            failure = error
            continue
        return plaintext.decode("utf-8")
    raise UndecryptableValue(
        "the configured encryption key is not the one that wrote this value"
    ) from failure


class EncryptedSecret(TypeDecorator[str]):
    """A ``str`` column that is ciphertext at rest (FR-018).

    Encrypts on the way in and decrypts on the way out, so a model declares an
    ordinary string attribute and the database holds bytes. Nothing that reads
    the table without the key — a dump, a replica, an operator with a psql
    session — sees anything but an envelope.

    ``cache_ok`` is true because the type carries no per-instance state: the key
    lives in ``KEY_RING``, so two ``EncryptedSecret()`` instances compile to the
    same statement and SQLAlchemy may cache it.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        """Return ``value`` sealed, or ``None``."""
        return None if value is None else seal(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        """Return the plaintext of a stored envelope, or ``None``."""
        return None if value is None else unseal(value)


__all__ = [
    "ENVELOPE_VERSION",
    "KEY_LENGTH_BYTES",
    "KEY_RING",
    "NONCE_LENGTH_BYTES",
    "EncryptedSecret",
    "EncryptionNotConfigured",
    "Envelope",
    "KeyRing",
    "UndecryptableValue",
    "decode_key",
    "generate_key",
    "seal",
    "unseal",
]
