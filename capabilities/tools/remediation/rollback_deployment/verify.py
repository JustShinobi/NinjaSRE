"""A deploy took effect when the running revision is the one that was asked for."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import FieldVerifier
from platform.remediation.models import RemediationAction, StateSnapshot


def intended(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the revision the workload should be on after the action."""
    del before
    return {"revision": action.arguments.get("target_revision")}


verifier = FieldVerifier(intended_of=intended)

__all__ = ["intended", "verifier"]
