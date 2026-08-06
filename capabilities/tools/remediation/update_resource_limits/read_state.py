"""The requests and limits a workload runs under.

All four, always, even when the action changes one. A plan that restored the
memory limit and silently left a CPU request somebody else had changed would
be a rollback that put the workload into a third state.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = (
    "cpu_request",
    "cpu_limit",
    "memory_request",
    "memory_limit",
)

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
