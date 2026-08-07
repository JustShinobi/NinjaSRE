"""Every timestamp moves by one offset, so every interval between them survives.

Determinism is the requirement — a visual-regression baseline captured against
live data is a photograph of one moment, and it differs on the next run because
a clock moved. But a dataset with all its timestamps set to the same instant is
not a history: nothing is four minutes ago, nothing is two days ago, and every
"most recent first" list is in arbitrary order.

So one offset, applied to everything. The latest instant in the capture lands on
a fixed reference instant, and every other timestamp keeps its distance from it.
The dataset is then reproducible *and* still reads as something that happened.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from config.constants.fixtures import FIXTURE_REFERENCE_INSTANT

#: ISO-8601 with a date, a ``T``, a time, and an optional fraction and offset.
#: Deliberately strict about the shape: a looser pattern matches version numbers
#: and a duration, and shifting either of those corrupts the record.
TIMESTAMP_PATTERN: Final = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\b"
)


def reference_instant() -> datetime:
    """Return the instant the latest timestamp in a capture is moved onto."""
    return datetime.fromisoformat(FIXTURE_REFERENCE_INSTANT)


def timestamps_in(document: Any) -> Iterator[str]:
    """Yield every ISO-8601 timestamp anywhere in ``document``, however nested."""
    if isinstance(document, Mapping):
        for value in document.values():
            yield from timestamps_in(value)
    elif isinstance(document, Sequence) and not isinstance(document, str | bytes):
        for item in document:
            yield from timestamps_in(item)
    elif isinstance(document, str):
        yield from TIMESTAMP_PATTERN.findall(document)


def offset_for(
    document: Any, target: datetime | None = None, *, anchor: datetime | None = None
) -> timedelta:
    """Return the one offset that moves ``anchor`` onto ``target``.

    ``anchor`` is the moment the capture was taken — the dataset's "now". Pass
    it. Falling back to the latest timestamp in the document is wrong whenever a
    record looks forward: a machine token that expires in a year would drag the
    entire history a year into the past, and every relative time on every screen
    would read as stale. That is not a hypothetical; it is what happened the
    first time this was written without an anchor.

    Zero when there is nothing to shift, which keeps an empty scenario stable
    rather than making it depend on the wall clock.
    """
    moment = target if target is not None else reference_instant()
    if anchor is not None:
        return moment - anchor
    parsed = [instant for instant in (_parse(raw) for raw in timestamps_in(document)) if instant]
    if not parsed:
        return timedelta(0)
    return moment - max(parsed)


def shift(document: Any, offset: timedelta) -> Any:
    """Return ``document`` with every timestamp moved by ``offset``.

    Format is preserved per timestamp: a value written with a ``Z`` comes back
    with a ``Z``, one written with an explicit offset keeps that offset, and one
    with no zone keeps none. A pipeline that normalised them would change what
    the console is asked to render.
    """
    if isinstance(document, Mapping):
        return {key: shift(value, offset) for key, value in document.items()}
    if isinstance(document, Sequence) and not isinstance(document, str | bytes):
        return [shift(item, offset) for item in document]
    if isinstance(document, str):
        return TIMESTAMP_PATTERN.sub(lambda found: _shift_one(found.group(0), offset), document)
    return document


def _shift_one(raw: str, offset: timedelta) -> str:
    instant = _parse(raw)
    if instant is None:
        return raw
    moved = instant + offset
    if raw.endswith("Z"):
        return moved.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if instant.tzinfo is None:
        return moved.replace(tzinfo=None).isoformat()
    return moved.isoformat()


def _parse(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = [
    "TIMESTAMP_PATTERN",
    "offset_for",
    "reference_instant",
    "shift",
    "timestamps_in",
]
