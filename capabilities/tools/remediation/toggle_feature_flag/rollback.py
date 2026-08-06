"""Putting a flag back to the value and rollout it had."""

from __future__ import annotations

from capabilities.tools.remediation._base import RestoreGenerator
from capabilities.tools.remediation.toggle_feature_flag.read_state import FIELDS
from platform.remediation.models import RemediationAction, StateSnapshot

TOOL_NAME = "toggle_feature_flag"


def describe(action: RemediationAction, before: StateSnapshot) -> str:
    """Return the sentence an engineer reads under pressure."""
    enabled = before.values.get("enabled")
    rollout = before.values.get("rollout")
    at = f" at a {rollout} rollout" if rollout not in (None, "") else ""
    return (
        f"Set {action.target.identifier} in "
        f"{action.target.environment or 'its environment'} back to "
        f"{'enabled' if enabled else 'disabled'}{at}."
    )


generator = RestoreGenerator(capability=TOOL_NAME, fields=FIELDS, describe=describe)

__all__ = ["TOOL_NAME", "describe", "generator"]
