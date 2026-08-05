"""Turning a name into a SQL identifier, or refusing to.

Almost everything in this package is a parameterised query, where the driver
keeps values and syntax apart and there is nothing to get wrong. Two things
cannot be: the per-generation vector tables, whose *names* encode a namespace,
and Apache AGE's ``cypher()``, whose graph name is a literal by construction.

For those, this module is the only place a name becomes syntax. It is short and
strict on purpose — a name either matches a conservative identifier pattern and
is quoted, or it raises. There is no escaping path, because escaping is the part
people get subtly wrong; rejecting is not.
"""

from __future__ import annotations

import re

#: Lowercase, starts with a letter, no consecutive punctuation. Narrower than
#: PostgreSQL allows, and narrower than any name this platform generates —
#: which is what makes rejection an acceptable answer.
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

#: PostgreSQL truncates identifiers at 63 bytes. A namespace long enough to be
#: truncated is one where two generations could collide into the same table.
MAX_IDENTIFIER_LENGTH = 63

#: Prefix for the tables holding one namespace's vectors, so a database dump
#: shows at a glance which tables the platform generated.
VECTOR_TABLE_PREFIX = "ninjasre_vec"


class UnsafeIdentifier(ValueError):
    """A name that would have to be escaped to be used as an identifier."""

    def __init__(self, name: str, *, reason: str) -> None:
        super().__init__(f"{name!r} cannot be used as a SQL identifier: {reason}")
        self.name = name
        self.reason = reason


def safe_identifier(name: str) -> str:
    """Return ``name`` if it is usable unescaped, or raise ``UnsafeIdentifier``."""
    if not _SAFE_IDENTIFIER.match(name):
        raise UnsafeIdentifier(
            name,
            reason="expected lowercase letters, digits, and underscores, starting with a letter",
        )
    if len(name) > MAX_IDENTIFIER_LENGTH:
        raise UnsafeIdentifier(
            name, reason=f"longer than PostgreSQL's {MAX_IDENTIFIER_LENGTH}-byte limit"
        )
    return name


def vector_table_name(namespace: str, generation: int) -> str:
    """Return the table holding one namespace generation's vectors.

    One table per generation rather than a generation column, because pgvector
    fixes a column's dimension at creation and a re-embed may change it
    (FR-014). Separate tables also make activation a pointer move and
    ``drop_generation`` a ``DROP TABLE`` — neither of which touches the rows
    searches are reading.
    """
    if generation < 1:
        raise UnsafeIdentifier(str(generation), reason="generations are numbered from 1")
    return safe_identifier(f"{VECTOR_TABLE_PREFIX}_{namespace}_g{generation}")


def quoted(name: str) -> str:
    """Return ``name`` validated and double-quoted, ready to interpolate."""
    return f'"{safe_identifier(name)}"'


__all__ = [
    "MAX_IDENTIFIER_LENGTH",
    "VECTOR_TABLE_PREFIX",
    "UnsafeIdentifier",
    "quoted",
    "safe_identifier",
    "vector_table_name",
]
