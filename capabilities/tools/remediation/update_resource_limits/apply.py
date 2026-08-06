"""Writing new requests and limits, leaving unnamed ones where they were."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier
from capabilities.tools.remediation.update_resource_limits.read_state import FIELDS
from platform.remediation.models import RemediationAction, StateSnapshot


def desired(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the full set of limits the workload should have afterwards.

    The whole set rather than the changed fields. A partial write is
    interpreted differently by different control planes — some merge, some
    replace — and a capability whose effect depends on which one is bound is
    not one anybody can approve.
    """
    return {name: action.arguments.get(name, before.values.get(name)) for name in FIELDS}


applier = ControlPlaneApplier(desired_of=desired)

__all__ = ["applier", "desired"]
