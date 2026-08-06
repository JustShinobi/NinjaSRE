"""Setting a workload's replica count."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the replica count this action asks for."""
    del before
    return {"replicas": action.arguments.get("replicas")}


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
