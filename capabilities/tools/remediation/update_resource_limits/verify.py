"""A limit change took effect when the workload reports the values asked for.

Worth verifying rather than assuming: a limit below what is already in use,
or above a namespace quota, is accepted by the API and then not applied.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import FieldVerifier
from capabilities.tools.remediation.update_resource_limits.read_state import FIELDS
from platform.remediation.models import RemediationAction, StateSnapshot


def intended(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the limits the workload should report after the action."""
    return {name: action.arguments[name] for name in FIELDS if name in action.arguments} or {
        name: before.values.get(name) for name in FIELDS
    }


verifier = FieldVerifier(intended_of=intended)

__all__ = ["intended", "verifier"]
