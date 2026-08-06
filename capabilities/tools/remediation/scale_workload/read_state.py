"""The replica count a scale changes and a rollback restores."""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation._base import ControlPlaneReader

FIELDS: Final[tuple[str, ...]] = ("replicas",)

reader = ControlPlaneReader(fields=FIELDS)

__all__ = ["FIELDS", "reader"]
