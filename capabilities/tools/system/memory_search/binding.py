"""How a declared tool reaches a run-scoped service without becoming one.

A capability is a plain function. Discovery finds it by walking a package, the
model calls it by name, and it has no constructor to pass a retriever to — which
is what makes the catalogue addable one package at a time and is not something to
give up for this one tool.

So the retriever is *bound* rather than injected: the composition root sets it
for the process, the tool reads it, and an unbound tool returns an explicit
unavailability instead of pretending. That is a global, and the honest thing to
say about a global is what it costs. Here it costs single-run-per-process
fidelity: two investigations in one process share whichever binding was set last.
That is acceptable today because a run is driven by one composition root and the
binding is set from it, and it is the reason ``bind`` returns a token that
``restore`` puts back — a caller that does want two can scope the binding around
its own run rather than leaving it set.

What is deliberately *not* here is a fallback. An unbound tool does not quietly
construct a retriever from ambient configuration: a tool that invented its own
tenant scope would be one search away from returning another team's incidents.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from platform.memory.models import RecallQuery
from platform.memory.retrieval import RecallResult


@runtime_checkable
class RecallSource(Protocol):
    """Whatever answers a recall.

    ``MemoryRetriever`` satisfies this structurally, and so does
    ``StrategyRecall`` — which is the whole reason playbooks arrive through this
    capability rather than through a second one. The composition root decides
    which of the two a deployment binds; the tool cannot tell them apart and does
    not need to.
    """

    async def search(self, query: RecallQuery) -> RecallResult:
        """Return the episodes resembling ``query``, ranked and team-scoped."""


_BOUND: RecallSource | None = None


def bind(source: RecallSource | None) -> RecallSource | None:
    """Bind ``source`` as the process's recall path and return what it replaced.

    The return value is what makes this safe to use in a test or around a single
    run: hold it, and put it back with ``restore`` when the scope ends.
    """
    global _BOUND
    previous = _BOUND
    _BOUND = source
    return previous


def restore(previous: RecallSource | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind recall, so the tool reports memory as unconfigured again."""
    restore(None)


def current() -> RecallSource | None:
    """Return the bound recall path, or ``None`` when memory is not configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "RecallSource",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
