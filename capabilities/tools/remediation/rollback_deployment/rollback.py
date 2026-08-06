"""Rolling a rollback back, which is a roll forward to the revision recorded first.

The step that matters is the *first* one: record what is running now, before
changing it. A plan that only said "put back the previous revision" would be
written against a revision nobody wrote down, and would be unusable at the
moment it was needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation._base import RestoreGenerator
from capabilities.tools.remediation.rollback_deployment.read_state import FIELDS
from core.capability.metadata import RollbackPlan as DeclaredRollbackPlan
from platform.remediation.models import RemediationAction, StateSnapshot

TOOL_NAME = "rollback_deployment"


@dataclass(frozen=True, slots=True)
class ReleaseRollbackPlanner:
    """Returns the deploy to the release it was on before."""

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing a rollback of the release in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        target = arguments.get("target_revision", "the previous revision")
        return DeclaredRollbackPlan(
            summary=(
                f"Re-deploy {workload} in {environment} to the revision it was running "
                f"before it was moved to {target}."
            ),
            steps=(
                f"Record the revision {workload} is on now, before changing it.",
                f"Deploy that recorded revision to {workload} in {environment}.",
                "Confirm the symptom that prompted the rollback has returned, "
                "which is what proves the rollback was the cause of the change.",
            ),
        )


def describe(action: RemediationAction, before: StateSnapshot) -> str:
    """Return the sentence an engineer reads under pressure."""
    revision = before.values.get("revision", "the revision it was on")
    environment = action.target.environment or "its environment"
    return f"Deploy {action.target.identifier} in {environment} back to revision {revision}."


generator = RestoreGenerator(capability=TOOL_NAME, fields=FIELDS, describe=describe)

__all__ = ["TOOL_NAME", "ReleaseRollbackPlanner", "describe", "generator"]
