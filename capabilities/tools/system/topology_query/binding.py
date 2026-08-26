"""How the topology capability reaches a run-scoped graph without becoming one.

The same arrangement the recall capability uses, and for the same reason: a
capability is a plain function that discovery finds by walking a package, so
there is no constructor to pass a tenant scope to. A composition root binds the
query path, the tool reads it, and an unbound tool returns an explicit
unavailability rather than pretending.

The binding lives in a ``ContextVar``, so it belongs to one investigation rather
than to the process. An investigation is an asyncio task and a task starts with
a copy of its parent's context: what a run binds is visible to everything that
run awaits and to no other run. A module-level global would instead be one cell
shared by every task here, and this deployment starts investigations
concurrently — so the second run to bind would become the graph the first one
traverses, on the other organisation's scope.

``bind`` returns what it displaced and ``restore`` puts it back, so a run
sharing its task with anything else leaves the context as it found it.

What is deliberately *not* here is a fallback. An unbound tool does not quietly
construct a query path from ambient configuration: a tool that invented its own
tenant scope would be one traversal away from returning another organisation's
topology.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from typing import Protocol, runtime_checkable

from platform.knowledge.topology.queries import ServiceTopology


@runtime_checkable
class TopologySource(Protocol):
    """Whatever answers a topology question.

    ``TopologyQueries`` satisfies this structurally. The protocol exists so the
    tool depends on the shape of the answer rather than on the class, which is
    what lets a deployment bind a decorated or instrumented one.
    """

    async def query(self, service: str, *, depth: int = ...) -> ServiceTopology:
        """Return what the graph knows about ``service``, or why it does not."""


#: This context's topology path. ``None`` by default in every context that has
#: not bound one, so a deployment that composed no graph reads an honest absence
#: rather than whatever the last run to finish left behind.
_BOUND: ContextVar[TopologySource | None] = ContextVar(
    "capabilities.tools.system.topology_query.source", default=None
)


def bind(source: TopologySource | None) -> TopologySource | None:
    """Bind ``source`` as this context's topology path and return what it replaced.

    Visible to this asyncio task and to every task it spawns, and to nothing
    else. The return value is what a caller scoping a binding around one run
    hands back to ``restore`` when that run ends.
    """
    previous = _BOUND.get()
    _BOUND.set(source)
    return previous


def restore(previous: TopologySource | None) -> None:
    """Put back a binding ``bind`` replaced, in the context that replaced it."""
    _BOUND.set(previous)


def clear() -> None:
    """Unbind topology, so the tool reports the graph as unconfigured again."""
    restore(None)


def current() -> TopologySource | None:
    """Return the bound topology path, or ``None`` when none is configured."""
    return _BOUND.get()


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report.

    Answers for the context that asks: what a health endpoint's own task can see
    is what it can honestly report.
    """
    source = _BOUND.get()
    return () if source is None else (type(source).__name__,)


__all__ = [
    "TopologySource",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
