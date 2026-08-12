"""How the log capability reaches a tenant-scoped reader without becoming one.

The arrangement the change capability already uses, for the same reason: a
capability is a plain function that discovery finds by walking a package, so
there is no constructor to hand a tenant scope to. The composition root binds the
path for the process, the tool reads it, and an unbound tool reports an explicit
unavailability.

There is deliberately no fallback. An unbound tool does not build a reader from
ambient configuration — a tool that invented its own scope would be one lookup
away from reading another organisation's logs.

Resolving a resource to its stream selector is on the bound object's side of the
seam, because it needs the estate and the deployment's selector rules. A tool
that composed selectors itself would be the second query language this
deployment has to keep working.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class LogSourceUnavailable(RuntimeError):
    """The log system did not answer, so nothing can be concluded from silence.

    This layer's own error rather than the observability bridge's, for the reason
    the answer shape is: the bridge is optional and a capability that imported it
    would make it mandatory. The composition that holds both translates.
    """


@runtime_checkable
class LogAnswerShape(Protocol):
    """What a tool needs of a log answer, and nothing else.

    Declared here rather than imported from the observability bridge: the bridge
    is an optional feature, and a capability that imported it would make it
    mandatory for every deployment. The bridge's own answer satisfies this
    structurally, which is the whole point of stating it as a protocol.
    """

    @property
    def summary(self) -> str:
        """Return the sentence that must accompany these lines wherever shown."""

    @property
    def complete(self) -> bool:
        """Return whether these lines are the whole answer to the question asked."""


@runtime_checkable
class LogAccess(Protocol):
    """Whatever answers "what do this resource's logs say".

    Returns ``None`` when the estate holds no such resource, or holds it and no
    selector rule applies to its kind. Both are different from an empty answer:
    one means nobody is watching the thing the alert named, the other means the
    guest was quiet.
    """

    async def logs_for(self, resource: str, *, at: datetime) -> Any | None:
        """Return the lines this resource's stream held, or ``None``."""


_BOUND: LogAccess | None = None


def bind(access: LogAccess | None) -> LogAccess | None:
    """Bind ``access`` as this process's log path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = access
    return previous


def restore(previous: LogAccess | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind, so the tool reports that no log source is configured."""
    restore(None)


def current() -> LogAccess | None:
    """Return the bound log path, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "LogAccess",
    "LogAnswerShape",
    "LogSourceUnavailable",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
