"""The encryption key, which the operator supplies and NinjaSRE never invents.

FR-019 is one sentence and it is the whole module: the key is supplied, never
generated silently. The reasoning is worth keeping next to the code, because the
convenient alternative looks harmless.

A key generated at first start has to be stored somewhere the process can read
it again — a container layer, a bind-mounted file, a compose file — and the
operator does not know it exists. Nothing goes wrong until the day they restore
a backup on another host and discover that every stored credential is
ciphertext under a key that went away with the old container. Requiring the key
makes key management a decision somebody made, on the day they had time to make
it.

The generator hint is a shell command rather than a NinjaSRE command on purpose.
An operator provisioning a deployment has not installed anything yet.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from typing import Final

from config.constants.persistence import (
    DATABASE_ENCRYPTION_KEY_BYTES,
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
)
from platform.startup.errors import EncryptionKeyInvalid, EncryptionKeyMissing

#: AES-256, restated here under the name this package's callers use.
ENCRYPTION_KEY_BYTES: Final[int] = DATABASE_ENCRYPTION_KEY_BYTES

#: What an operator types to produce one. OpenSSL rather than a NinjaSRE
#: command, because the key has to exist before the deployment does.
KEY_GENERATOR_HINT: Final = f"`openssl rand -base64 {ENCRYPTION_KEY_BYTES}`"


def decode_encryption_key(material: str) -> bytes:
    """Return the key ``material`` encodes.

    Raises ``EncryptionKeyInvalid`` naming which way it is wrong — bad base64
    and the wrong length are different mistakes with different fixes, and a
    single "invalid key" would leave an operator guessing which they made.
    """
    try:
        key = base64.b64decode(material.strip(), validate=True)
    except (ValueError, TypeError) as error:
        raise EncryptionKeyInvalid(
            NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
            problem=f"it is not valid base64; generate one with {KEY_GENERATOR_HINT}",
        ) from error
    if len(key) != ENCRYPTION_KEY_BYTES:
        raise EncryptionKeyInvalid(
            NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
            problem=(
                f"it decodes to {len(key)} bytes and AES-256 needs "
                f"{ENCRYPTION_KEY_BYTES}; generate one with {KEY_GENERATOR_HINT}"
            ),
        )
    return key


def configured_key(environ: Mapping[str, str] | None = None) -> bytes | None:
    """Return the configured key, or ``None`` when the operator supplied none.

    ``None`` rather than an exception, because a deployment that stores no
    credentials is legitimate. ``require_encryption_key`` is what the credential
    path calls, and it is the one that refuses.
    """
    source = environ if environ is not None else os.environ
    material = source.get(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV, "").strip()
    if not material:
        return None
    return decode_encryption_key(material)


def require_encryption_key(environ: Mapping[str, str] | None = None) -> bytes:
    """Return the configured key, or raise ``EncryptionKeyMissing`` (FR-019)."""
    key = configured_key(environ)
    if key is None:
        raise EncryptionKeyMissing(
            NINJASRE_DATABASE_ENCRYPTION_KEY_ENV, generator_hint=KEY_GENERATOR_HINT
        )
    return key


def key_fingerprint(key: bytes) -> str:
    """Return a short, non-reversible label for ``key``, safe to log.

    Twelve hex characters of a SHA-256 digest. Enough for an operator to see
    that two hosts hold the same key, and far too little to reconstruct one —
    which matters, because the realistic use is a support conversation where
    somebody pastes the whole log.
    """
    import hashlib

    return hashlib.sha256(key).hexdigest()[:12]


__all__ = [
    "ENCRYPTION_KEY_BYTES",
    "KEY_GENERATOR_HINT",
    "configured_key",
    "decode_encryption_key",
    "key_fingerprint",
    "require_encryption_key",
]
