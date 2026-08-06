"""Whether a node accepts work, and what is running on it.

Both, because the two halves of this action have different undos. Cordoning
is reversed by uncordoning; draining is not reversed at all — the workloads
have already been rescheduled elsewhere and putting them back is not
something anybody wants.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = ("schedulable", "workloads")

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
