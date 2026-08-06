"""A scale took effect when the replica count is the one that was asked for."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import FieldVerifier
from platform.remediation.models import RemediationAction, StateSnapshot


def intended(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the replica count the workload should have after the action."""
    del before
    return {"replicas": action.arguments.get("replicas")}


verifier = FieldVerifier(intended_of=intended)

__all__ = ["intended", "verifier"]
