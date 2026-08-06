"""Putting the replica count back to the number that was recorded."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation._base import RestoreGenerator
from capabilities.tools.remediation.scale_workload.read_state import FIELDS
from core.capability.metadata import RollbackPlan as DeclaredRollbackPlan
from platform.remediation.models import RemediationAction, StateSnapshot

TOOL_NAME = "scale_workload"


@dataclass(frozen=True, slots=True)
class ScaleRollbackPlanner:
    """Returns the replica count to the number it was at."""

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing a scale of the workload in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        replicas = arguments.get("replicas", "the requested count")
        return DeclaredRollbackPlan(
            summary=(
                f"Scale {workload} in {environment} from {replicas} back to the count "
                "recorded before the change."
            ),
            steps=(
                f"Read and store the current replica count for {workload}.",
                f"Set {workload} in {environment} back to the stored count.",
                "Confirm the workload is stable at the restored count.",
            ),
        )


def describe(action: RemediationAction, before: StateSnapshot) -> str:
    """Return the sentence an engineer reads under pressure."""
    recorded = before.values.get("replicas", "the recorded count")
    requested = action.arguments.get("replicas", "the requested count")
    return (
        f"Scale {action.target.identifier} in "
        f"{action.target.environment or 'its environment'} from {requested} back to "
        f"{recorded} replica(s)."
    )


generator = RestoreGenerator(capability=TOOL_NAME, fields=FIELDS, describe=describe)

__all__ = ["TOOL_NAME", "ScaleRollbackPlanner", "describe", "generator"]
