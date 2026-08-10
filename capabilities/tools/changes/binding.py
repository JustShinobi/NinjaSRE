"""How the change capability reaches a tenant-scoped inquiry without becoming one.

The arrangement the topology and recall capabilities already use, for the same
reason: a capability is a plain function that discovery finds by walking a
package, so there is no constructor to hand a tenant scope to. The composition
root binds the path for the process, the tool reads it, and an unbound tool
reports an explicit unavailability.

There is deliberately no fallback. An unbound tool does not construct an inquiry
from ambient configuration — a tool that invented its own scope would be one
lookup away from reading another organisation's estate, and one directory read
away from a repository nobody pointed it at.

The bound object answers one question, and the resource lookup is on its side of
the seam on purpose. Resolving "which resource is this" needs the estate, the
tenant scope and the alert's own naming conventions; putting it here would mean
either the capability held a gateway or the estate leaked into the tool layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from platform.changes.models import ChangeWindow
from platform.changes.service import ChangeAnswer


@runtime_checkable
class ChangeAccess(Protocol):
    """Whatever answers "what changed for this resource".

    Returns ``None`` for a resource the estate does not hold, which is a
    different outcome from "nothing changed" and leads somewhere different: one
    is a finding, the other is an alert naming something nobody is watching.
    """

    async def changes_for(self, resource: str, *, window: ChangeWindow) -> ChangeAnswer | None:
        """Return what changed for ``resource`` in ``window``, or ``None``."""


_BOUND: ChangeAccess | None = None


def bind(access: ChangeAccess | None) -> ChangeAccess | None:
    """Bind ``access`` as this process's change path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = access
    return previous


def restore(previous: ChangeAccess | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind, so the tool reports that no change source is configured."""
    restore(None)


def current() -> ChangeAccess | None:
    """Return the bound change path, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "ChangeAccess",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
