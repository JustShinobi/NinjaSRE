"""How a remediation reaches the system it is changing, without knowing which one.

Restarting a workload, changing a replica count, and cordoning a node are the
same three actions whether the control plane is Kubernetes, ECS, or a fleet of
virtual machines. Putting one narrow port in front of all of them is what stops
the approval rules, the rollback shapes, and the verification comparisons being
re-implemented — slightly differently — once per vendor.

Two operations and nothing else. ``read`` says what the target holds; ``change``
makes it hold something else and reports what happened to each piece. There is
deliberately no operation that takes a command, because a port that accepted one
would be the place a generated string eventually reached a production API.

**Binding is explicit and there is no fallback.** An unbound control plane makes
every remediation capability report itself unavailable, by name. A tool that
constructed its own client from ambient configuration would be one credential
lookup away from acting on somebody else's estate, and "it worked in
development" is how that ships.

**Nothing here carries a credential.** The implementation a deployment binds
reaches its vendor through the credential proxy like every other authenticated
call; what this port passes is the action and the desired state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from platform.remediation.models import RemediationAction, StateSnapshot, SubTargetResult


@dataclass(frozen=True, slots=True)
class ControlPlaneState:
    """What the control plane says a target currently holds.

    ``sub_targets`` is the list of pieces an action can act on individually —
    the pods behind a deployment, the nodes in a pool. It is read *before* the
    change so partial success can be expressed against something that was
    recorded rather than against whatever the failure happened to mention.
    """

    values: Mapping[str, Any] = field(default_factory=dict)
    sub_targets: tuple[str, ...] = ()


@runtime_checkable
class ControlPlane(Protocol):
    """The two things a remediation needs of the system it changes."""

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        """Return what the target holds, or ``None`` when it cannot be read.

        ``None`` means "we could not tell", which is a different fact from an
        empty reading and must not be collapsed into one: the first blocks the
        action and the second does not.
        """

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        """Return what happened to each piece of the target.

        One result per piece that was attempted, and a piece that was already in
        the desired state comes back with ``changed=False`` — it was not altered
        and must not appear in the rollback plan as something to put back.
        """


_BOUND: ControlPlane | None = None


def bind(plane: ControlPlane | None) -> ControlPlane | None:
    """Bind ``plane`` as the process's control plane and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = plane
    return previous


def restore(previous: ControlPlane | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind the control plane, so every remediation reports itself unavailable."""
    restore(None)


def current() -> ControlPlane | None:
    """Return the bound control plane, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "ControlPlane",
    "ControlPlaneState",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
