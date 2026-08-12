"""What a node is publishing through the observability bridge, without this
package ever importing the bridge.

A structural rule of this repository: the hypervisor integration and the rest of the
catalogue work with no bridge configured at all, so nothing under
``integrations/`` may depend on ``platform.observation.bridge`` — a structural
test walks the whole tree and fails the build on the import. So a tool that
wants a node's current readings asks this instead: one binding per process,
set by whoever composes the deployment, over a plain callable that carries no
bridge type across the boundary. ``integrations/proxmox/supplementary.py``
already reads its input the same way, as a plain ``Mapping``, for the same
reason.

**A deployment with no bridge configured binds nothing.** A tool reading
``current()`` as ``None`` reports itself unavailable by name, the same shape
``integrations/_base/access.py`` uses for the credential proxy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

#: One node's name in, what it is publishing out — in the shape
#: ``integrations.proxmox.supplementary.supplementary_readings`` reads.
NodeReadings = Callable[[str], Awaitable[Mapping[str, Any]]]


class NodeReadingsUnavailable(Exception):
    """The bound reader could not answer — the metrics system did not respond."""


_BOUND: NodeReadings | None = None


def bind(reader: NodeReadings | None) -> NodeReadings | None:
    """Bind ``reader`` for this process and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = reader
    return previous


def restore(previous: NodeReadings | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind, so a caller reading ``current()`` finds nothing."""
    restore(None)


def current() -> NodeReadings | None:
    """Return this process's bound reader, or ``None`` when nothing composed one."""
    return _BOUND


__all__ = ["NodeReadings", "NodeReadingsUnavailable", "bind", "clear", "current", "restore"]
