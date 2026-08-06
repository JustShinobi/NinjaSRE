"""What a restart is verified against: which processes were running before it.

Not a replica count and not a health status. A restart's effect is that the
processes are *different ones*, and the only way to check that afterwards is
to have written down which ones there were. A verifier comparing counts would
pass on a restart that never happened.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

#: The field a restart is about. ``instances`` rather than ``pods`` because
#: this capability is cross-vendor and a task, a container, and a pod are the
#: same idea under three names.
FIELDS: Final[tuple[str, ...]] = ("instances",)

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
