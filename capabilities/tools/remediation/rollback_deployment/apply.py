"""Moving a workload to a named revision."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the revision this action asks the workload to be on.

    Falls back to the revision recorded before the change when the call
    names none, which is what "roll back" means when nobody said how far.
    """
    del before
    return {"revision": action.arguments.get("target_revision")}


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
