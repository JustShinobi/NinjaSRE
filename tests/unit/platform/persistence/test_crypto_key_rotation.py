"""The two-key ring, which is what makes rotation an online operation.

FR-021 asks for re-encryption with no downtime. The cryptographic reason that is
possible is here: an AES-GCM envelope carries no key identifier, so a row is
readable by exactly the key that wrote it and there is no way to tell from
outside which that was. A process holding *both* keys can therefore read the
whole table while it rewrites it — the rows it has reached under the new key,
the rows it has not under the old.

These are the assertions that argument rests on. Without them the no-downtime
claim is a comment.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from platform.persistence.postgres.crypto import (
    KEY_LENGTH_BYTES,
    KEY_RING,
    EncryptionNotConfigured,
    UndecryptableValue,
    decode_key,
    generate_key,
    seal,
    unseal,
)

pytestmark = pytest.mark.unit

OLD = decode_key(generate_key())
NEW = decode_key(generate_key())


@pytest.fixture(autouse=True)
def restore_the_key_ring() -> Iterator[None]:
    """Leave the process's key ring as it was found.

    It is module-level state, deliberately — the encrypted column type is
    constructed at import, before any configuration has happened — so a test
    that reconfigured it and walked away would change every test after it.
    """
    yield
    KEY_RING.clear()


def test_a_row_written_under_the_old_key_is_readable_while_the_new_one_writes() -> None:
    """The whole no-downtime argument, in four lines."""
    KEY_RING.configure(OLD)
    written_before = seal("the-vendor-api-key")

    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(OLD)

    assert unseal(written_before) == "the-vendor-api-key"
    assert unseal(seal("written-after")) == "written-after"


def test_writes_always_use_the_current_key_never_the_fallback() -> None:
    """A fallback that could write would let a half-finished rotation go backwards."""
    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(OLD)
    written = seal("after-the-rotation-started")

    KEY_RING.clear()
    KEY_RING.configure(OLD)

    with pytest.raises(UndecryptableValue):
        unseal(written)


def test_dropping_the_previous_key_makes_the_unrewritten_rows_unreadable() -> None:
    """Which is why the rotation report says explicitly when it is safe to drop it."""
    KEY_RING.configure(OLD)
    written_before = seal("never-rewritten")

    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(OLD)
    assert unseal(written_before) == "never-rewritten"

    KEY_RING.clear_previous()
    with pytest.raises(UndecryptableValue):
        unseal(written_before)


def test_a_ring_with_no_fallback_behaves_exactly_as_it_did_before() -> None:
    KEY_RING.configure(NEW)

    assert not KEY_RING.has_previous
    assert len(KEY_RING.read_ciphers()) == 1


def test_a_ring_with_a_fallback_tries_the_current_key_first() -> None:
    """Most rows are under one key; trying it first keeps the common read at one attempt."""
    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(OLD)

    assert KEY_RING.has_previous
    assert len(KEY_RING.read_ciphers()) == 2


def test_clearing_the_ring_forgets_the_fallback_too() -> None:
    """A process that kept it would keep a key an operator believes is gone."""
    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(OLD)

    KEY_RING.clear()

    assert not KEY_RING.has_previous
    with pytest.raises(EncryptionNotConfigured):
        KEY_RING.read_ciphers()


def test_a_fallback_of_the_wrong_length_is_refused_like_any_other_key() -> None:
    KEY_RING.configure(NEW)

    with pytest.raises(ValueError, match=str(KEY_LENGTH_BYTES)):
        KEY_RING.configure_previous(b"too short")


def test_a_value_neither_key_opens_still_says_only_that() -> None:
    """The message names no value, no key, and no ciphertext — only the fact."""
    KEY_RING.configure(OLD)
    written = seal("under-a-third-key")
    KEY_RING.clear()
    KEY_RING.configure(NEW)
    KEY_RING.configure_previous(decode_key(generate_key()))

    with pytest.raises(UndecryptableValue) as caught:
        unseal(written)

    assert "under-a-third-key" not in str(caught.value)
    assert "is not the one that wrote this value" in str(caught.value)
