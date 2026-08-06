"""Restoring every request and limit the workload had, not just the changed one."""

from __future__ import annotations

from capabilities.tools.remediation._base import RestoreGenerator
from capabilities.tools.remediation.update_resource_limits.read_state import FIELDS
from platform.remediation.models import RemediationAction, StateSnapshot

TOOL_NAME = "update_resource_limits"


def describe(action: RemediationAction, before: StateSnapshot) -> str:
    """Return the sentence an engineer reads under pressure."""
    listed = ", ".join(
        f"{name}={before.values.get(name)!r}" for name in FIELDS if before.values.get(name)
    )
    return (
        f"Restore {action.target.identifier} in "
        f"{action.target.environment or 'its environment'} to {listed or 'its prior limits'}."
    )


generator = RestoreGenerator(capability=TOOL_NAME, fields=FIELDS, describe=describe)

__all__ = ["TOOL_NAME", "describe", "generator"]
