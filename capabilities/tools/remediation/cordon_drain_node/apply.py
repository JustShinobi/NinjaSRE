"""Marking a node unschedulable, and optionally moving what is on it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the node state this action asks for.

    ``drain`` defaults to ``False``. Cordoning is the reversible half and
    draining is not, so an argument nobody supplied resolves to the one that
    can be undone.
    """
    del before
    return {
        "schedulable": False,
        "drain": bool(action.arguments.get("drain", False)),
    }


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
