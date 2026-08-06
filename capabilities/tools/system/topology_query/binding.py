"""How the topology capability reaches a run-scoped graph without becoming one.

The same arrangement the recall capability uses, and for the same reason: a
capability is a plain function that discovery finds by walking a package, so
there is no constructor to pass a tenant scope to. The composition root binds the
query path for the process, the tool reads it, and an unbound tool returns an
explicit unavailability rather than pretending.

What is deliberately *not* here is a fallback. An unbound tool does not quietly
construct a query path from ambient configuration: a tool that invented its own
tenant scope would be one traversal away from returning another organisation's
topology.
"""

from __future__ import annotations

from collections.abc import Sequence
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


_BOUND: TopologySource | None = None


def bind(source: TopologySource | None) -> TopologySource | None:
    """Bind ``source`` as the process's topology path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = source
    return previous


def restore(previous: TopologySource | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind topology, so the tool reports the graph as unconfigured again."""
    restore(None)


def current() -> TopologySource | None:
    """Return the bound topology path, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "TopologySource",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
