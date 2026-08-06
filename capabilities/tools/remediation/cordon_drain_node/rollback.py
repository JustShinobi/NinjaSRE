"""Uncordoning, and saying plainly that the drained workloads do not come back.

The plan restores schedulability and stops there. Listing "move the pods
back" as a step would be a step nobody should run: they were rescheduled,
they are healthy where they are, and moving them a second time is another
disruption for no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass

from capabilities.tools.remediation._base import steps_for
from platform.remediation.models import RemediationAction, RollbackPlan, StateSnapshot

TOOL_NAME = "cordon_drain_node"


@dataclass(frozen=True, slots=True)
class UncordonGenerator:
    """Produces the plan that makes the node schedulable again."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the uncordon plan, or ``None`` when the node could not be read."""
        if not before.known:
            return None
        node = action.target.identifier
        drained = bool(action.arguments.get("drain", False))
        note = (
            " The workloads that were drained stay where they were rescheduled; "
            "moving them back is a second disruption for no benefit."
            if drained
            else ""
        )
        return RollbackPlan(
            plan_id="",
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=f"Make {node} schedulable again.{note}",
            steps=steps_for(
                action,
                capability=TOOL_NAME,
                descriptions=(f"Set {node} back to schedulable.",),
                arguments={"schedulable": True, "drain": False},
            ),
        )


generator = UncordonGenerator()

__all__ = ["TOOL_NAME", "UncordonGenerator", "generator"]
