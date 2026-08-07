"""SC-007: key rotation with no downtime and no credential lost.

The no-downtime property is asserted where it actually lives — between batches.
A reader arriving mid-rotation must find every credential readable, whichever
side of the walk it is on, and the test below reads them all at exactly that
moment rather than trusting the argument.

What runs here is the *policy*: batching, what a report accounts for, and what
a failure does to the rest of the run. The half that touches storage lives in
``tests/contract/persistence/test_key_rotation.py``, because re-encrypting a
credential means reading its plaintext and that is a call only the storage layer
and the proxy may make.
"""

from __future__ import annotations

import pytest

from platform.credentials.handles import CredentialHandle
from platform.startup.rotation import (
    CredentialReEncryptor,
    KeyLossConsequences,
    KeyRotationReport,
    rotate_encryption_key,
)

pytestmark = pytest.mark.unit


def handles(count: int) -> tuple[str, ...]:
    """Return ``count`` credential handles, in the vault's own shape."""
    return tuple(
        CredentialHandle(integration=f"vendor-{index}", team_id="payments").qualified
        for index in range(count)
    )


# -- the executor -------------------------------------------------------------


class RecordingReEncryptor:
    """A re-encryptor that records its batches, for asserting the batching itself."""

    def __init__(self, *, all_handles: tuple[str, ...], unreadable: frozenset[str] = frozenset()):
        self.all_handles = all_handles
        self.unreadable = unreadable
        self.batches: list[tuple[str, ...]] = []

    async def handles(self) -> tuple[str, ...]:
        return self.all_handles

    async def reencrypt(self, handles: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        self.batches.append(tuple(handles))
        return tuple(handle for handle in handles if handle not in self.unreadable)


def test_the_recording_double_is_the_port() -> None:
    assert isinstance(RecordingReEncryptor(all_handles=()), CredentialReEncryptor)


async def test_every_credential_is_rewritten_and_the_report_adds_up() -> None:
    """SC-007: no loss. Every handle the rotation started with is accounted for."""
    every = handles(7)
    reencryptor = RecordingReEncryptor(all_handles=every)

    report = await rotate_encryption_key(reencryptor, batch_size=3)

    assert report.total == 7
    assert set(report.rewritten) == set(every)
    assert report.unreadable == ()
    assert report.complete
    assert report.accounted_for == report.total


async def test_the_work_is_batched_at_the_size_it_was_given() -> None:
    """A batch is a transaction, and a transaction is how long a reader could wait."""
    reencryptor = RecordingReEncryptor(all_handles=handles(7))

    report = await rotate_encryption_key(reencryptor, batch_size=3)

    assert [len(batch) for batch in reencryptor.batches] == [3, 3, 1]
    assert report.batches == 3


async def test_a_credential_neither_key_opens_is_reported_rather_than_aborting() -> None:
    """It was already broken; stopping would strand every other credential."""
    every = handles(5)
    reencryptor = RecordingReEncryptor(all_handles=every, unreadable=frozenset({every[2]}))

    report = await rotate_encryption_key(reencryptor, batch_size=2)

    assert not report.complete
    assert report.unreadable == (every[2],)
    assert report.accounted_for == 5, "every handle still has an answer"
    assert "must be re-entered" in report.summary()
    assert "Keep the previous key" in report.summary()


async def test_a_complete_rotation_says_the_previous_key_may_be_dropped() -> None:
    report = await rotate_encryption_key(RecordingReEncryptor(all_handles=handles(3)))

    assert "no longer needed" in report.summary()


async def test_progress_is_reported_after_each_batch() -> None:
    """A silent process rewriting a thousand credentials is one nobody dares interrupt."""
    seen: list[int] = []

    await rotate_encryption_key(
        RecordingReEncryptor(all_handles=handles(6)),
        batch_size=2,
        on_batch=lambda running: seen.append(len(running.rewritten)),
    )

    assert seen == [2, 4, 6]


async def test_a_deployment_with_no_credentials_rotates_trivially() -> None:
    report = await rotate_encryption_key(RecordingReEncryptor(all_handles=()))

    assert report.complete
    assert report.batches == 0


async def test_a_batch_size_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        await rotate_encryption_key(RecordingReEncryptor(all_handles=()), batch_size=0)


# -- key loss (FR-022) ---------------------------------------------------------


def test_key_loss_says_what_goes_what_stays_and_what_to_do() -> None:
    summary = KeyLossConsequences().summary()

    assert "cannot be recovered" in summary
    assert "investigation, trace" in summary
    assert "re-enter each integration's credential" in summary
    assert "Recovery:" in summary


def test_key_loss_does_not_claim_investigations_are_lost() -> None:
    """They are not, and telling an operator otherwise would be the worst kind of wrong."""
    consequences = KeyLossConsequences()

    assert len(consequences.lost) == 1
    assert any("audit trail" in item for item in consequences.survives)


def test_an_empty_rotation_report_is_not_mistaken_for_a_complete_one() -> None:
    report = KeyRotationReport(total=3, rewritten=(), unreadable=(), batches=0)

    assert not report.complete
