"""A flag change took effect when the provider reports the value asked for."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation._base import FieldVerifier
from platform.remediation.models import RemediationAction, StateSnapshot


def intended(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the flag state the action intended."""
    return {
        "enabled": action.arguments.get("enabled"),
        "rollout": action.arguments.get("rollout", before.values.get("rollout")),
    }


verifier = FieldVerifier(intended_of=intended)

__all__ = ["intended", "verifier"]
