"""The one path into the dataset. Everything that writes a fixture comes through here.

There is deliberately a single function, and every producer calls it: the
gateway capture, the infrastructure projection, an ad-hoc answer somebody
recorded from a terminal, and the scenario builder. A finding that reached the
dataset by a different route is a finding the scan never saw, and the second
route is always added for a good reason by somebody in a hurry.

An architecture test asserts that nothing else writes into the scenario tree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tools.mockplane.anonymise.pseudonyms import PseudonymBook
from tools.mockplane.anonymise.redaction import anonymise, dropped_fields
from tools.mockplane.anonymise.timeshift import offset_for, reference_instant, shift
from tools.mockplane.identifiers import IdentifierList
from tools.mockplane.records import CapturedRecord


@dataclass(frozen=True, slots=True)
class ProcessedCapture:
    """What the pipeline produced, and what it took out on the way."""

    records: tuple[CapturedRecord, ...]
    #: How far every timestamp moved. Reported because "the dataset is two days
    #: older than the capture" is the first question about a fixture that looks
    #: stale.
    offset: timedelta
    #: Pointers to every field that was dropped rather than renamed, so a
    #: reviewer can see that a capture carried credentials and where.
    removed: tuple[str, ...] = field(default_factory=tuple)


def process(
    records: Sequence[CapturedRecord],
    *,
    book: PseudonymBook,
    identifiers: IdentifierList,
    instant: datetime | None = None,
    captured_at: datetime | None = None,
) -> ProcessedCapture:
    """Return ``records`` anonymised, credential-free and shifted onto a fixed instant.

    Order matters and is not adjustable.

    Credentials are removed *before* renaming, so a token is never handed to the
    pseudonym derivation — which would put its hash in the book and its shape in
    the output. Renaming happens before the shift, so the offset is computed
    over the timestamps that will actually be written. And the shift is applied
    last, over the whole set at once, because an offset computed per record
    would move two records by different amounts and destroy the interval
    between them, which is the one property the shift exists to preserve.

    ``captured_at`` is the dataset's "now" and is what lands on the reference
    instant. Without it the shift anchors on the latest timestamp anywhere in
    the capture, and one token expiring next year drags the whole history back
    with it.
    """
    renamed = [record.with_body(anonymise(record.body, book, identifiers)) for record in records]
    bodies = [record.body for record in renamed]
    offset = offset_for(
        bodies,
        instant if instant is not None else reference_instant(),
        anchor=captured_at,
    )
    shifted = tuple(record.with_body(shift(record.body, offset)) for record in renamed)
    removed = tuple(
        f"{record.slug}{pointer}" for record in shifted for pointer in dropped_fields(record.body)
    )
    return ProcessedCapture(records=shifted, offset=offset, removed=removed)


__all__ = ["ProcessedCapture", "process"]
