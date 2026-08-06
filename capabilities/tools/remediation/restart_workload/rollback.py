"""The honest plan for a restart, which is a recovery rather than a reversal.

A restart cannot be undone: the previous processes are gone and their
in-flight requests with them. Saying so is the plan. What the steps carry is
the recovery an engineer would actually run if the restart made things worse
— confirm readiness, and if it did not come back, roll the release back
rather than restarting a second time.

The steps are what make this a plan rather than a shrug, and ``reversible``
is ``False`` so nothing downstream reads it as an undo it can rely on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation._base import steps_for
from core.capability.metadata import RollbackPlan as DeclaredRollbackPlan
from platform.remediation.models import RemediationAction, RollbackPlan, StateSnapshot


@dataclass(frozen=True, slots=True)
class RestartRollbackPlanner:
    """Names what a restart cannot undo, which is the honest plan for one."""

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing a restart of the workload in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        return DeclaredRollbackPlan(
            summary=(
                f"A restart of {workload} in {environment} cannot be undone: the "
                "previous process is gone and its in-flight requests with it."
            ),
            steps=(
                f"Confirm {workload} reached a ready state in {environment}.",
                "If it did not, the recovery is the rollback tool, not a second restart.",
                "Re-run the queries that established the symptom, to see whether it moved.",
            ),
            reversible=False,
        )


@dataclass(frozen=True, slots=True)
class RestartRecovery:
    """Produces the recovery steps a restart is followed by, never a reversal."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the recovery plan, or ``None`` when the prior state is unknown."""
        if not before.known:
            return None
        workload = action.target.identifier
        return RollbackPlan(
            plan_id="",
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=(
                f"A restart of {workload} cannot be undone. If it made things worse, "
                f"roll the release back rather than restarting again."
            ),
            reversible=False,
            steps=steps_for(
                action,
                capability="rollback_deployment",
                descriptions=(
                    f"Confirm {workload} reached a ready state.",
                    f"If it did not, roll {workload} back to its previous revision.",
                ),
            ),
        )


generator = RestartRecovery()

__all__ = ["RestartRecovery", "RestartRollbackPlanner", "generator"]
