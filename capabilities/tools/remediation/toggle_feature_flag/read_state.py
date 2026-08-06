"""A flag's value, and the rollout it is at.

Both, because a flag is rarely a boolean in practice. "On for 10% of
traffic" and "on" are different states, and a rollback that restored the
first as the second would turn a mitigation into a launch.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = ("enabled", "rollout")

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
