"""Configuration paths: the dotted strings everything else in this package uses.

A path names one field — ``policies.masking.level`` — and is the identifier a
lock, a required-field policy, a provenance entry, an audit row, and a
validation error all agree on. Keeping the four functions that manipulate one in
a single module is what stops a lock's idea of "covers" drifting from the
merge's.

**A prefix is not a cover.** ``policies.mask`` does not cover
``policies.masking``, and the difference is a segment boundary rather than a
string prefix. Getting that wrong locks a field nobody meant to lock, which is
the kind of bug an operator experiences as the platform being arbitrary.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from config.constants.config_service import PATH_SEPARATOR


def join(segments: Iterable[str]) -> str:
    """Return the dotted path for ``segments``."""
    return PATH_SEPARATOR.join(segments)


def split(path: str) -> tuple[str, ...]:
    """Return the segments of ``path``."""
    return tuple(path.split(PATH_SEPARATOR)) if path else ()


def prefixes(path: str) -> Iterator[str]:
    """Yield ``path`` and every ancestor path of it, shortest first.

    ``policies.masking.level`` yields ``policies``, ``policies.masking``, then
    itself. That is the set a lock lookup tests, and yielding shortest-first
    means the outermost lock is the one reported.
    """
    segments = split(path)
    for depth in range(1, len(segments) + 1):
        yield join(segments[:depth])


def covers(pattern: str, path: str) -> bool:
    """Return whether ``pattern`` names ``path`` or an ancestor of it.

    Segment-aware: ``policies.mask`` does not cover ``policies.masking``.
    """
    return path == pattern or path.startswith(pattern + PATH_SEPARATOR)


def value_at(values: Mapping[str, Any], path: str) -> Any:
    """Return the value at ``path``, or ``None`` if nothing is set there.

    ``None`` is ambiguous with an explicitly-null value on purpose. Every caller
    that needs to tell them apart has the provenance map, which records the one
    and not the other.
    """
    cursor: Any = values
    for segment in split(path):
        if not isinstance(cursor, Mapping) or segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def leaves(values: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield every ``(path, value)`` in ``values`` that is not a mapping.

    A list is a leaf. That is the merge's view of the world — lists replace
    entirely — and provenance, locks, and change detection all have to agree
    with it, or a lock on a list would mean something different from the
    replacement the merge performs.

    An empty mapping yields itself, because it is a value somebody set. A
    non-empty one yields only what is inside it.
    """
    for key, value in values.items():
        path = f"{prefix}{PATH_SEPARATOR}{key}" if prefix else key
        if isinstance(value, Mapping) and value:
            yield from leaves(value, path)
        else:
            yield path, value


def scalars(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield every scalar reachable in ``value``, descending into lists as well.

    Deliberately different from ``leaves``: this one looks *inside* a list, at
    ``integrations.active.0.credential``. It exists for the secret scan, which
    has to see every string an operator wrote regardless of what structure it
    sits in — a credential pasted into the third entry of a list is a
    credential. Nothing about merge semantics is expressed here, which is why
    it is a second function rather than a flag on the first.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from scalars(item, f"{prefix}{PATH_SEPARATOR}{key}" if prefix else str(key))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield from scalars(item, f"{prefix}{PATH_SEPARATOR}{index}")
    else:
        yield prefix, value


__all__ = ["covers", "join", "leaves", "prefixes", "scalars", "split", "value_at"]
