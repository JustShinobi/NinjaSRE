"""Which revision is running, which is what a rollback moves and restores.

Read before the action so the plan can name the revision to come back to.
"Roll it forward again" is not a plan; "deploy revision 41f2c to checkout-api
in production" is, and the difference is what the read produces.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = ("revision",)

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
