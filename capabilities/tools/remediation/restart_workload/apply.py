"""Replacing a workload's processes, one result per instance.

The desired state is expressed as the instances that should be gone rather
than as a command, because that is what makes partial success meaningful:
three of five replaced is three results with ``changed=True`` and two with
``changed=False``, and the rollback plan is scoped to the three.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the state a restart asks the control plane for."""
    return {
        "action": "restart",
        "replace": list(before.sub_targets or ()),
        "grace_seconds": action.arguments.get("grace_seconds"),
    }


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
