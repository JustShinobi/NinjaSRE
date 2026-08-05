"""Reading what AGE returns.

``agtype`` is JSON with a type suffix — ``{"id": 1125…, "label": "Node",
"properties": {…}}::vertex`` — and asyncpg hands it back as that string, because
it is a type the driver has never heard of. Stripping the suffix and parsing the
rest is all the decoding this package needs, and doing it in one module means
the repositories never see a string that looks like JSON but is not.

Node properties round-trip through here too. AGE refuses ``SET n += $map``, so
arbitrary properties are stored as one JSON-encoded string and unpacked on the
way out. That is a storage detail rather than a modelling one: the port's
``TopologyNode.properties`` is a mapping at both ends.
"""

from __future__ import annotations

import json
from typing import Any

#: Suffixes AGE appends to a value to say what it is. Order matters only in that
#: every one has to be tried; a vertex and a path both end in something.
_TYPE_SUFFIXES = ("::vertex", "::edge", "::path")

#: The node property holding the caller's arbitrary properties, JSON-encoded.
PROPERTIES_KEY = "properties"


def strip_suffix(raw: str) -> str:
    """Return ``raw`` without its agtype suffix."""
    for suffix in _TYPE_SUFFIXES:
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw


def loads(raw: str | None) -> Any:
    """Return the Python value an agtype string encodes, or ``None``.

    A list of vertices arrives as one JSON array whose *elements* carry the
    suffixes, so the strip has to happen inside as well as outside — which is
    why this reaches for a targeted replace rather than parsing twice.
    """
    if raw is None:
        return None
    text = strip_suffix(raw.strip())
    for suffix in _TYPE_SUFFIXES:
        text = text.replace(suffix, "")
    return json.loads(text)


def properties_of(raw: str | None) -> dict[str, Any]:
    """Return the properties map of a vertex, or an empty one."""
    value = loads(raw)
    if isinstance(value, dict):
        # ``properties(n)`` returns the map itself; ``RETURN n`` returns the
        # whole vertex with the map under a key. Both reach here.
        inner = value.get(PROPERTIES_KEY)
        return dict(inner) if isinstance(inner, dict) else dict(value)
    return {}


def encode_properties(properties: dict[str, Any]) -> str:
    """Return ``properties`` as the single JSON string AGE will store."""
    return json.dumps(properties, sort_keys=True, default=str)


def decode_properties(stored: Any) -> dict[str, Any]:
    """Return the properties map a stored JSON string holds."""
    if isinstance(stored, str) and stored:
        decoded = json.loads(stored)
        return dict(decoded) if isinstance(decoded, dict) else {}
    if isinstance(stored, dict):
        return dict(stored)
    return {}


def as_int(raw: str | None) -> int:
    """Return the integer an agtype scalar holds."""
    value = loads(raw)
    return int(value) if value is not None else 0


__all__ = [
    "PROPERTIES_KEY",
    "as_int",
    "decode_properties",
    "encode_properties",
    "loads",
    "properties_of",
    "strip_suffix",
]
