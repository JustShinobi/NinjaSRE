"""Bringing a payload inside the trace's bounds, and saying what that cost.

A capability can return forty megabytes of logs. The trace has to hold something
about that call, the database has to stay a database, and the person reading the
trace afterwards has to be able to tell the difference between "the tool
returned four lines" and "the tool returned four hundred thousand and we kept
four". That last requirement is the whole module: **cutting is fine, cutting
silently is not.**

So every reduction leaves two traces of itself. The value carries a visible
suffix, because that is what a human reads first, and the payload carries a
marker object under one known key, because that is what a console or an
evaluation harness reads. A truncation that showed up in neither would be a
payload that lies about being complete.

Four reductions, applied in this order because each makes the next cheaper:
long strings, long sequences, deep nesting, and — only if the result is still
over the byte ceiling — dropping whole top-level values, largest first. The last
one is a blunt instrument and is meant to be: by the time it runs, the payload
has already refused three gentler bounds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from config.constants.runs import (
    MAX_TRACE_PAYLOAD_BYTES,
    MAX_TRACE_PAYLOAD_DEPTH,
    MAX_TRACE_SEQUENCE_ITEMS,
    MAX_TRACE_STRING_LENGTH,
    TRUNCATION_MARKER_KEY,
    TRUNCATION_SUFFIX,
)

#: What replaces a branch below the depth ceiling. Carries the suffix so the
#: same string search finds every kind of reduction in a rendered payload.
_DEPTH_MARKER = f"<nested{TRUNCATION_SUFFIX}>"


@dataclass(frozen=True, slots=True)
class Bounds:
    """The four ceilings one reduction applies.

    Carried as a value rather than read from the constants at each step,
    because there is more than one reader of a payload and they do not want the
    same size. Writing to the trace wants the storage bound; serving a whole
    run's calls in one response wants a much tighter one, and re-implementing
    the reduction for the second reader would mean two vocabularies of marker
    for the same fact — that something was cut.
    """

    payload_bytes: int = MAX_TRACE_PAYLOAD_BYTES
    string_length: int = MAX_TRACE_STRING_LENGTH
    depth: int = MAX_TRACE_PAYLOAD_DEPTH
    sequence_items: int = MAX_TRACE_SEQUENCE_ITEMS


#: What the recorder writes under. The default, so an existing caller keeps the
#: bounds it already had.
TRACE_BOUNDS: Final = Bounds()


@dataclass(frozen=True, slots=True)
class Truncation:
    """What a payload lost on its way into the trace."""

    strings: int = 0
    items: int = 0
    branches: int = 0
    fields: int = 0
    bytes_removed: int = 0

    @property
    def happened(self) -> bool:
        """Return whether anything was removed at all."""
        return bool(self.strings or self.items or self.branches or self.fields)

    def as_marker(self) -> dict[str, int]:
        """Return the record written beside the payload it describes."""
        return {
            "strings": self.strings,
            "items": self.items,
            "branches": self.branches,
            "fields": self.fields,
            "bytes_removed": self.bytes_removed,
        }


def truncate(
    payload: Mapping[str, Any], *, bounds: Bounds = TRACE_BOUNDS
) -> tuple[dict[str, Any], Truncation]:
    """Return ``payload`` reduced to ``bounds``, and what was removed from it.

    The returned mapping is JSON-serialisable whatever went in: a value the
    encoder cannot represent becomes its ``repr``. A payload that raised on the
    way into the store would be a trace that never happened, and Article I is
    explicit that a result which never entered the trace did not happen.
    """
    counter = _Counter()
    reduced = {
        key: _walk(value, depth=1, counter=counter, bounds=bounds) for key, value in payload.items()
    }

    before = _size(reduced)
    if before > bounds.payload_bytes:
        reduced = _shed(reduced, counter=counter, bounds=bounds)
        counter.bytes_removed += before - _size(reduced)

    removal = counter.result()
    if removal.happened:
        reduced[TRUNCATION_MARKER_KEY] = removal.as_marker()
    return reduced, removal


@dataclass(slots=True)
class _Counter:
    """The running tally one call to ``truncate`` accumulates."""

    strings: int = 0
    items: int = 0
    branches: int = 0
    fields: int = 0
    bytes_removed: int = 0

    def result(self) -> Truncation:
        """Return the immutable summary of what was counted."""
        return Truncation(
            strings=self.strings,
            items=self.items,
            branches=self.branches,
            fields=self.fields,
            bytes_removed=self.bytes_removed,
        )


def _walk(value: Any, *, depth: int, counter: _Counter, bounds: Bounds) -> Any:
    """Return ``value`` reduced to the structural bounds, counting as it goes."""
    if depth > bounds.depth:
        counter.branches += 1
        return _DEPTH_MARKER

    if isinstance(value, str):
        if len(value) <= bounds.string_length:
            return value
        counter.strings += 1
        counter.bytes_removed += len(value[bounds.string_length :].encode("utf-8"))
        return value[: bounds.string_length] + TRUNCATION_SUFFIX

    if isinstance(value, Mapping):
        return {
            str(key): _walk(item, depth=depth + 1, counter=counter, bounds=bounds)
            for key, item in value.items()
        }

    # ``str`` and ``bytes`` are sequences and are handled above and below; what
    # is left here is the list-shaped thing a tool result actually carries.
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = list(value)
        if len(items) > bounds.sequence_items:
            counter.items += len(items) - bounds.sequence_items
            items = items[: bounds.sequence_items]
        return [_walk(item, depth=depth + 1, counter=counter, bounds=bounds) for item in items]

    if isinstance(value, bool | int | float) or value is None:
        return value

    # Anything else — a datetime, a dataclass, a vendor client's response
    # object. Its ``repr`` is worse than a schema and infinitely better than an
    # exception raised while recording what a capability returned.
    return _walk(repr(value), depth=depth, counter=counter, bounds=bounds)


def _shed(payload: dict[str, Any], *, counter: _Counter, bounds: Bounds) -> dict[str, Any]:
    """Return ``payload`` with its largest fields dropped until it fits.

    Largest first, because the alternative — dropping in key order — removes an
    arbitrary number of small fields to make room for one big one that stays.
    The marker key is never a candidate: it is what tells the reader this
    happened.
    """
    reduced = dict(payload)
    by_size = sorted(
        (key for key in reduced if key != TRUNCATION_MARKER_KEY),
        key=lambda key: _size(reduced[key]),
        reverse=True,
    )
    for key in by_size:
        if _size(reduced) <= bounds.payload_bytes:
            break
        reduced[key] = f"<dropped{TRUNCATION_SUFFIX}>"
        counter.fields += 1
    return reduced


def _size(value: Any) -> int:
    """Return the byte length of ``value``'s JSON form, or of its repr."""
    try:
        return len(json.dumps(value).encode("utf-8"))
    except (TypeError, ValueError):  # pragma: no cover — ``_walk`` removes these
        return len(repr(value).encode("utf-8"))


__all__ = ["TRACE_BOUNDS", "Bounds", "Truncation", "truncate"]
