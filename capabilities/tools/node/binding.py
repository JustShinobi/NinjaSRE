"""How the node capability reaches an executor without becoming one.

The arrangement the change and log capabilities already use. A capability is a
plain function discovery finds by walking a package, so there is no constructor
to hand a tenant scope to: the composition root binds the path for the process
and the tool reads it.

**Nothing here knows what an executor is.** The shape of a result is declared as
a protocol rather than imported, because the executor lives in ``gateway/`` and a
capability that imported it would invert the tiers — and because the thing that
holds an SSH key should not be something this layer can reach at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class NodeOutcome(Protocol):
    """What a tool needs of an execution result, and nothing else.

    Four outcomes live in these fields, and keeping them apart is the whole
    contract: ran and was content, ran and was unhappy, was refused, could not
    be reached.
    """

    @property
    def refused(self) -> bool:
        """Return whether the command was not something the allowlist permits."""

    @property
    def unreachable(self) -> bool:
        """Return whether nobody could ask the node at all."""


@runtime_checkable
class NodeAccess(Protocol):
    """Whatever can run a declared command on a node."""

    async def run(self, *, node: str, command_id: str) -> Any:
        """Return what running ``command_id`` on ``node`` produced."""


_BOUND: NodeAccess | None = None


def bind(access: NodeAccess | None) -> NodeAccess | None:
    """Bind ``access`` as this process's executor path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = access
    return previous


def restore(previous: NodeAccess | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind, so the tool reports that no executor is configured."""
    restore(None)


def current() -> NodeAccess | None:
    """Return the bound executor path, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "NodeAccess",
    "NodeOutcome",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
