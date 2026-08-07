"""Re-encrypting every stored credential under a new key, while the platform runs.

FR-021 asks for rotation with no downtime, and the shape of the answer follows
from one fact about how the rows are stored: a credential is AES-GCM ciphertext
whose envelope carries no key identifier, so a row is readable by exactly the
key that wrote it and there is no way to tell from the outside which that was.

Which means a rotation cannot be atomic and does not need to be. The process
doing it holds *both* keys — the new one for writing, the old one as a fallback
for reading — so at every instant during the run, every row is readable: the
ones already rewritten under the new key, the ones not yet reached under the
old. Nothing is offline, and a reader that arrives mid-rotation notices nothing.
That is the whole no-downtime argument, and it is why ``KeyRing`` grew a
previous key rather than this module growing a maintenance window.

Batching is what keeps the *write* side out of the way. One transaction per
batch, sized so no single transaction holds credential rows long enough to block
an investigation that needs to read one, and small enough that a failure loses a
batch's worth of work rather than a thousand credentials' worth.

A failure does not stop the run. A single credential whose ciphertext opens with
neither key is already broken — it survived a previous restore without its key —
and aborting the rotation over it would leave the rest of the deployment
straddling two keys indefinitely. It is recorded, reported, and the run
continues, which is why the report accounts for every handle rather than
counting successes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from config.constants.deployment import KEY_ROTATION_BATCH_SIZE


@runtime_checkable
class CredentialReEncryptor(Protocol):
    """Rewrites stored credentials under the process's current encryption key."""

    async def handles(self) -> tuple[str, ...]:
        """Return every stored credential handle in this tenant, in a stable order."""

    async def reencrypt(self, handles: Sequence[str]) -> tuple[str, ...]:
        """Rewrite each of ``handles`` under the current key, in one transaction.

        Returns the handles that were rewritten. A handle whose ciphertext opens
        with no key the process holds is omitted rather than raised on: it is
        already unreadable, and stopping the rotation would leave every other
        credential straddling two keys.
        """


@dataclass(frozen=True, slots=True)
class KeyRotationReport:
    """What a rotation touched, and what it could not.

    ``complete`` is the property SC-007 turns into an assertion: every handle
    the rotation started with is accounted for, either rewritten or named as
    unreadable. A report where the two do not add up is a rotation that lost
    something.
    """

    total: int = 0
    rewritten: tuple[str, ...] = ()
    unreadable: tuple[str, ...] = ()
    batches: int = 0
    key_fingerprint: str = ""

    @property
    def complete(self) -> bool:
        """Return whether every credential is now under the new key."""
        return not self.unreadable and len(self.rewritten) == self.total

    @property
    def accounted_for(self) -> int:
        """Return how many of the starting handles the report has an answer for."""
        return len(self.rewritten) + len(self.unreadable)

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the rotation script prints."""
        return {
            "total": self.total,
            "rewritten": list(self.rewritten),
            "unreadable": list(self.unreadable),
            "batches": self.batches,
            "complete": self.complete,
            "key_fingerprint": self.key_fingerprint,
        }

    def summary(self) -> str:
        """Return the line an operator reads to know whether they may drop the old key."""
        head = (
            f"re-encrypted {len(self.rewritten)} of {self.total} credential(s) "
            f"in {self.batches} batch(es)"
        )
        if self.complete:
            return f"{head}; the previous key is no longer needed"
        if self.unreadable:
            listed = ", ".join(self.unreadable)
            return (
                f"{head}; {len(self.unreadable)} could not be read with either key "
                f"and must be re-entered: {listed}. Keep the previous key until they are."
            )
        return f"{head}; keep the previous key until a run reports every credential rewritten"


async def rotate_encryption_key(
    reencryptor: CredentialReEncryptor,
    *,
    batch_size: int = KEY_ROTATION_BATCH_SIZE,
    key_fingerprint: str = "",
    on_batch: Callable[[KeyRotationReport], None] | None = None,
) -> KeyRotationReport:
    """Re-encrypt every stored credential under the process's current key (FR-021).

    ``on_batch`` is called with the running report after each batch — a long
    rotation on a large deployment should be able to say how far it has got,
    and the alternative is an operator watching a silent process.

    Raises:
        ValueError: ``batch_size`` is not positive.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    handles = await reencryptor.handles()
    rewritten: list[str] = []
    unreadable: list[str] = []
    batches = 0

    for start in range(0, len(handles), batch_size):
        batch = handles[start : start + batch_size]
        done = await reencryptor.reencrypt(batch)
        batches += 1
        rewritten.extend(done)
        unreadable.extend(handle for handle in batch if handle not in set(done))
        if on_batch is not None:
            on_batch(
                KeyRotationReport(
                    total=len(handles),
                    rewritten=tuple(rewritten),
                    unreadable=tuple(unreadable),
                    batches=batches,
                    key_fingerprint=key_fingerprint,
                )
            )

    return KeyRotationReport(
        total=len(handles),
        rewritten=tuple(rewritten),
        unreadable=tuple(unreadable),
        batches=batches,
        key_fingerprint=key_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class KeyLossConsequences:
    """What is lost with the encryption key, and what is not (FR-022).

    Written down as a value rather than as prose in a document, because the
    operator who needs it is looking at a failed startup rather than at the
    documentation, and the startup can print this.
    """

    lost: tuple[str, ...] = field(
        default=(
            "every stored integration credential, which is AES-256-GCM ciphertext "
            "under the lost key and cannot be recovered by any means",
        )
    )
    survives: tuple[str, ...] = field(
        default=(
            "every investigation, trace, and piece of evidence",
            "the episode corpus and the strategies synthesised from it",
            "the service topology and the knowledge base",
            "configuration, identity, roles, and the audit trail",
        )
    )
    recovery: tuple[str, ...] = field(
        default=(
            "generate a new key and configure it",
            "delete the unreadable credential rows, which startup names for you",
            "re-enter each integration's credential — they are re-enterable, which is "
            "what makes key loss unpleasant rather than terminal",
            "rotate the credentials at the vendor, since a lost key is usually lost "
            "alongside whatever else was on that host",
        )
    )

    def summary(self) -> str:
        """Return the block startup prints when it finds credentials it cannot open."""
        lines = ["Lost with the encryption key:"]
        lines.extend(f"  - {item}" for item in self.lost)
        lines.append("Unaffected:")
        lines.extend(f"  - {item}" for item in self.survives)
        lines.append("Recovery:")
        lines.extend(f"  {index}. {item}" for index, item in enumerate(self.recovery, start=1))
        return "\n".join(lines)


__all__ = [
    "CredentialReEncryptor",
    "KeyLossConsequences",
    "KeyRotationReport",
    "rotate_encryption_key",
]
