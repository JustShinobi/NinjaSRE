"""Duplicate tool calls, served from memory and named as repeats.

A model that has forgotten it already ran a query will run it again, and the
expensive part is not the vendor round trip. It is the iteration: the loop
spends one of twenty on a call whose answer was already in the transcript, and
the run ends having gathered less evidence than its budget allowed.

Saving the round trip is the easy half. The half that matters is
``replay_text``: the result comes back wrapped in a sentence saying the model
already holds it. Returning the payload bare reads as a fresh answer, and a
model that thinks it learned something new asks the same question a third time.

The cache is per loop, never shared with a sub-agent. A specialist re-fetching
what its parent already had is a real inefficiency in the trajectory, and the
evaluation suite should be able to see it rather than have it silently absorbed.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.investigation import (
    INVESTIGATION_TOOL_CACHE_MAX_CHARS,
    INVESTIGATION_TOOL_CACHE_MAX_ENTRIES,
)
from config.prompts.investigation import DUPLICATE_TOOL_CALL_REPLAY


def _canonical(value: Any) -> Any:
    """Return ``value`` in a form two equivalent argument objects share.

    Mappings are sorted, sequences keep their order, and anything else falls
    back to ``repr``. The fallback is what makes this total: a model can put
    anything in an argument object, and a cache that raised on an unexpected
    type would turn a cosmetic problem into a lost turn.
    """
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, str | bytes):
        return value.decode() if isinstance(value, bytes) else value
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return repr(value)


def cache_key(name: str, arguments: Mapping[str, Any]) -> str:
    """Return the key ``name`` called with ``arguments`` is stored under.

    Argument order is not part of the identity. Providers serialise an object's
    keys in whatever order they produced them, and two calls that differ only in
    that are the same call — which is precisely the duplicate this exists to
    catch.
    """
    return json.dumps(
        {"name": name, "arguments": _canonical(arguments)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


@dataclass(frozen=True, slots=True)
class CachedCall:
    """One result held for replay, with the evidence the original produced."""

    key: str
    capability: str
    content: str
    is_error: bool = False
    evidence_ids: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        """Return the stored result's size in characters."""
        return len(self.content)

    def replay_text(self) -> str:
        """Return the result wrapped in the notice that it is a repeat."""
        return DUPLICATE_TOOL_CALL_REPLAY.format(capability=self.capability, content=self.content)


@dataclass(slots=True)
class ToolCallCache:
    """Per-run duplicate detection, bounded by both entry count and size.

    Both bounds are needed. A count alone lets one enormous result sit in memory
    for the whole run; a size alone lets a thousand tiny ones accumulate. LRU
    order comes from ``OrderedDict``, which is what makes "the entry nobody has
    looked at" the one that goes.
    """

    max_entries: int = INVESTIGATION_TOOL_CACHE_MAX_ENTRIES
    max_chars: int = INVESTIGATION_TOOL_CACHE_MAX_CHARS
    _entries: OrderedDict[str, CachedCall] = field(default_factory=OrderedDict, repr=False)
    _chars: int = field(default=0, repr=False)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def stored_chars(self) -> int:
        """Return the characters currently held."""
        return self._chars

    def get(self, name: str, arguments: Mapping[str, Any]) -> CachedCall | None:
        """Return the stored result for this exact call, or ``None``."""
        key = cache_key(name, arguments)
        found = self._entries.get(key)
        if found is None:
            return None
        self._entries.move_to_end(key)
        return found

    def put(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        content: str,
        is_error: bool = False,
        evidence_ids: tuple[str, ...] = (),
    ) -> CachedCall:
        """Store one result and return the entry, evicting to stay within bounds.

        An entry larger than the whole character budget is returned but never
        stored: admitting it would evict everything else to hold one result, and
        the run would then have no duplicate detection at all for the sake of
        the single largest thing it fetched.
        """
        key = cache_key(name, arguments)
        entry = CachedCall(
            key=key,
            capability=name,
            content=content,
            is_error=is_error,
            evidence_ids=evidence_ids,
        )

        existing = self._entries.pop(key, None)
        if existing is not None:
            self._chars -= existing.size

        if entry.size > self.max_chars:
            return entry

        self._entries[key] = entry
        self._chars += entry.size
        self._evict()
        return entry

    def _evict(self) -> None:
        """Drop least-recently-used entries until both bounds hold."""
        while self._entries and (
            len(self._entries) > self.max_entries or self._chars > self.max_chars
        ):
            _, dropped = self._entries.popitem(last=False)
            self._chars -= dropped.size


__all__ = [
    "CachedCall",
    "ToolCallCache",
    "cache_key",
]
