"""How the knowledge capability reaches a run-scoped corpus without becoming one.

The same arrangement the recall and topology capabilities use. The composition
root binds the search path for the process, the tool reads it, and an unbound
tool returns an explicit unavailability.

No fallback, deliberately. A tool that constructed its own search path would
invent its own tenant scope, and one search later it would be returning another
team's runbooks.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from platform.knowledge.base.search import KnowledgeQuery, KnowledgeResult


@runtime_checkable
class KnowledgeSource(Protocol):
    """Whatever answers a knowledge search."""

    async def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Return the passages resembling ``query``, citable and team-scoped."""


_BOUND: KnowledgeSource | None = None


def bind(source: KnowledgeSource | None) -> KnowledgeSource | None:
    """Bind ``source`` as the process's knowledge path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = source
    return previous


def restore(previous: KnowledgeSource | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind the knowledge base, so the tool reports it as unconfigured again."""
    restore(None)


def current() -> KnowledgeSource | None:
    """Return the bound knowledge path, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "KnowledgeSource",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
