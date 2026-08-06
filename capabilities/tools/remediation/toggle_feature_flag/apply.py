"""Setting a flag's value and its rollout."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the flag state this action asks for."""
    return {
        "enabled": action.arguments.get("enabled"),
        "rollout": action.arguments.get("rollout", before.values.get("rollout")),
    }


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
