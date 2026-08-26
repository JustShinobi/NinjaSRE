"""How a declared tool reaches a run-scoped service without becoming one.

A capability is a plain function. Discovery finds it by walking a package, the
model calls it by name, and it has no constructor to pass a retriever to — which
is what makes the catalogue addable one package at a time and is not something to
give up for this one tool.

So the retriever is *bound* rather than injected: a composition root sets it, the
tool reads it, and an unbound tool returns an explicit unavailability instead of
pretending.

The binding lives in a ``ContextVar``, which is what makes it a property of one
investigation rather than of the process. An investigation is an asyncio task,
and a task starts with a copy of its parent's context: what a run binds is
visible to everything that run awaits and invisible to every other run, and it
goes away with the task rather than having to be cleaned up. A module-level
global has none of that — it is one cell for the whole process, so of two
investigations running together the second to bind silently becomes the source
the first one reads. This deployment starts them within milliseconds of each
other, and for recall that is not a stale answer but another team's incidents:
``MemoryRetriever`` refuses a scope with no team on it for exactly this reason.

``bind`` still returns what it displaced and ``restore`` still puts it back,
because a run that shares its task with something else — a test, a nested call,
a composition root that binds a default at boot — has to leave the context as it
found it.

What is deliberately *not* here is a fallback. An unbound tool does not quietly
construct a retriever from ambient configuration: a tool that invented its own
tenant scope would be one search away from returning another team's incidents.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
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


#: This context's recall path. ``None`` by default in every context that has not
#: bound one, so a deployment that composed no memory reads an honest absence
#: rather than whatever the last run to finish happened to leave behind.
_BOUND: ContextVar[RecallSource | None] = ContextVar(
    "capabilities.tools.system.memory_search.source", default=None
)


def bind(source: RecallSource | None) -> RecallSource | None:
    """Bind ``source`` as this context's recall path and return what it replaced.

    Visible to this asyncio task and to every task it goes on to spawn, and to
    nothing else. The return value is what makes this safe around a single run:
    hold it, and put it back with ``restore`` when the scope ends.
    """
    previous = _BOUND.get()
    _BOUND.set(source)
    return previous


def restore(previous: RecallSource | None) -> None:
    """Put back a binding ``bind`` replaced, in the context that replaced it."""
    _BOUND.set(previous)


def clear() -> None:
    """Unbind recall, so the tool reports memory as unconfigured again."""
    restore(None)


def current() -> RecallSource | None:
    """Return the bound recall path, or ``None`` when memory is not configured."""
    return _BOUND.get()


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report.

    Answers for the context that asks, which is the only honest scope: what a
    health endpoint's own task can see is what it can report on.
    """
    source = _BOUND.get()
    return () if source is None else (type(source).__name__,)


__all__ = [
    "RecallSource",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
