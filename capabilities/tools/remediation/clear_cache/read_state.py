"""How much is in the cache, which is the only thing worth recording about it.

Not the entries themselves. A cache large enough to matter is a cache too
large to snapshot, and pretending otherwise would produce a rollback plan
that could not be executed — which is worse than the honest answer that
there is not one.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = ("entries", "hit_rate")

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
