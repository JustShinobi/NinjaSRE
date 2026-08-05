"""The cipher behind FR-018, and the promises FR-019 makes about failure.

Runs without a database. The column type's job is to make what reaches the table
opaque, and whether it does is a property of ``seal`` and ``unseal`` rather than
of PostgreSQL — the at-rest check against real bytes lives in the contract suite.

What is worth testing here is the set of ways this could be subtly wrong and
still appear to work: a nonce that repeats, an envelope that decrypts under the
wrong key, an exception that carries the plaintext it was refusing to hand over.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest

from platform.persistence.postgres.crypto import (
    ENVELOPE_VERSION,
    KEY_LENGTH_BYTES,
    KEY_RING,
    NONCE_LENGTH_BYTES,
    EncryptionNotConfigured,
    Envelope,
    KeyRing,
    UndecryptableValue,
    decode_key,
    generate_key,
    seal,
    unseal,
)

pytestmark = pytest.mark.unit

SECRET = "xoxb-not-a-real-slack-token-000"


@pytest.fixture(autouse=True)
def configured_key() -> Iterator[None]:
    """Install a key for the duration of one test, and take it away after."""
    KEY_RING.configure(decode_key(generate_key()))
    yield
    KEY_RING.clear()


def test_a_sealed_value_comes_back() -> None:
    assert unseal(seal(SECRET)) == SECRET


def test_the_stored_form_contains_no_trace_of_the_plaintext() -> None:
    sealed = seal(SECRET)

    assert SECRET.encode("utf-8") not in sealed
    assert b"xoxb" not in sealed


def test_every_write_uses_a_fresh_nonce() -> None:
    """Reusing a nonce under GCM is a break, not a weakness.

    Two seals of the same plaintext must share nothing. If they did, an operator
    with read access to the table could tell which integrations hold the same
    credential — and worse is available to anybody who knows what nonce reuse
    costs in GCM.
    """
    nonces = {Envelope.from_bytes(seal(SECRET)).nonce for _ in range(64)}

    assert len(nonces) == 64
    assert all(len(nonce) == NONCE_LENGTH_BYTES for nonce in nonces)


def test_two_seals_of_one_secret_are_different_ciphertexts() -> None:
    assert seal(SECRET) != seal(SECRET)


def test_a_tampered_ciphertext_is_refused_rather_than_decrypted() -> None:
    """Authenticated encryption, and the reason it matters here.

    A store that could be tampered into returning an attacker's value would be
    worse than one with no encryption at all, because it would be trusted.
    """
    sealed = bytearray(seal(SECRET))
    sealed[-1] ^= 0x01

    with pytest.raises(UndecryptableValue):
        unseal(bytes(sealed))


def test_the_wrong_key_fails_loudly_and_says_nothing_useful() -> None:
    sealed = seal(SECRET)
    KEY_RING.configure(decode_key(generate_key()))

    with pytest.raises(UndecryptableValue) as failure:
        unseal(sealed)

    message = str(failure.value)
    assert SECRET not in message
    assert "key" in message.lower()


def test_a_value_that_is_not_an_envelope_is_told_apart_from_a_wrong_key() -> None:
    # The likely cause is a botched plaintext migration, and an operator
    # chasing a key problem that is not one loses an evening.
    with pytest.raises(UndecryptableValue, match="too short"):
        unseal(b"nope")


def test_an_envelope_from_a_future_release_is_refused_by_version() -> None:
    envelope = Envelope.from_bytes(seal(SECRET))
    future = Envelope(
        version=ENVELOPE_VERSION + 1,
        nonce=envelope.nonce,
        ciphertext=envelope.ciphertext,
    )

    with pytest.raises(UndecryptableValue, match="version"):
        unseal(future.to_bytes())


def test_a_key_of_the_wrong_length_is_refused_rather_than_stretched() -> None:
    ring = KeyRing()

    with pytest.raises(ValueError, match=str(KEY_LENGTH_BYTES)):
        ring.configure(b"too short")


@pytest.mark.parametrize(
    ("material", "reason"),
    [
        ("not base64 at all!!", "base64"),
        (base64.b64encode(b"sixteen bytes!!!").decode(), "AES-256"),
    ],
)
def test_bad_key_material_is_rejected_with_the_reason(material: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        decode_key(material)


def test_a_generated_key_is_usable() -> None:
    ring = KeyRing()
    ring.configure(decode_key(generate_key()))

    assert ring.is_configured is True
    ring.clear()
    assert ring.is_configured is False


def test_encrypting_without_a_key_says_which_variable_to_set() -> None:
    KEY_RING.clear()

    with pytest.raises(EncryptionNotConfigured, match="NINJASRE_DATABASE_ENCRYPTION_KEY"):
        seal(SECRET)
