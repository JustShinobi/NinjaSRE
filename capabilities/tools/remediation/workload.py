"""Restart, roll back, and scale — the three actions, with their undo declared first.

Each is declared with a planner that turns the specific arguments of one call
into the specific steps that reverse it. "Scale it back" is not a rollback
plan; "scale checkout-api in production from 12 back to 4 replicas" is, and the
difference is what an engineer at 3am can act on without reconstructing what
the agent was thinking.

The planners run at declaration-checking time and at approval time. Neither
depends on the execution that is a later feature — which is deliberate, because
a rollback plan that can only be produced by the code that performs the action
is a rollback plan that does not exist when the action fails halfway.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import (
    EvidenceType,
    RollbackPlan,
    SideEffectLevel,
)
from core.capability.result import CapabilityErrorClass, CapabilityResult

#: Remediation reaches a control plane through the credential proxy, and the
#: proxy is a later feature. Until then every action refuses, by name, rather
#: than half-performing.
_NOT_YET_EXECUTABLE = (
    "Remediation execution is not enabled in this deployment. The action, its "
    "approval requirement, and its rollback plan are declared; performing it "
    "needs the change-approval and rollback services."
)

_RESTART_USE_CASES = (
    "clear a workload stuck in a state a restart resolves, after the cause is known",
    "recover a service whose connection pool has become unusable",
)

_RESTART_ANTI_EXAMPLES = (
    "restarting before the cause is understood, which destroys the evidence",
    "restarting a workload whose failure will recur immediately",
)

_ROLLBACK_USE_CASES = (
    "return a service to the previous release after a deploy correlates with the alert",
    "undo a configuration change identified as the trigger",
)

_SCALE_USE_CASES = (
    "add capacity to a workload saturating its current replicas",
    "reduce a replica count raised during an earlier incident",
)


@dataclass(frozen=True, slots=True)
class RestartRollbackPlanner:
    """Names what a restart cannot undo, which is the honest plan for one."""

    def plan(self, arguments: Mapping[str, Any]) -> RollbackPlan:
        """Return the plan reversing a restart of the workload in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        return RollbackPlan(
            summary=(
                f"A restart of {workload} in {environment} cannot be undone: the "
                "previous process is gone and its in-flight requests with it."
            ),
            steps=(
                f"Confirm {workload} reached a ready state in {environment}.",
                "If it did not, the recovery is the rollback tool, not a second restart.",
                "Re-run the queries that established the symptom, to see whether it moved.",
            ),
            # The word is doing real work: the caller must know that approving
            # this is approving something that is not reversible by re-running
            # the tool with different arguments.
            reversible=False,
        )


@dataclass(frozen=True, slots=True)
class ReleaseRollbackPlanner:
    """Returns the deploy to the release it was on before."""

    def plan(self, arguments: Mapping[str, Any]) -> RollbackPlan:
        """Return the plan reversing a rollback of the release in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        target = arguments.get("target_revision", "the previous revision")
        return RollbackPlan(
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


@dataclass(frozen=True, slots=True)
class ScaleRollbackPlanner:
    """Returns the replica count to the number it was at."""

    def plan(self, arguments: Mapping[str, Any]) -> RollbackPlan:
        """Return the plan reversing a scale of the workload in ``arguments``."""
        workload = arguments.get("workload", "the workload")
        environment = arguments.get("environment", "the environment")
        replicas = arguments.get("replicas", "the requested count")
        return RollbackPlan(
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


@tool(
    name="restart_workload",
    display_name="Restart a workload",
    description=(
        "Restart a workload's instances. Drops in-flight requests and destroys the "
        "process state an investigation may still need, so use only after the cause "
        "is established."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Restarting drops every in-flight request and destroys the process state that "
        "would explain the failure. Neither is recoverable."
    ),
    rollback_planner=RestartRollbackPlanner(),
    tags=("remediation", "restart", "workload"),
    use_cases=_RESTART_USE_CASES,
    anti_examples=_RESTART_ANTI_EXAMPLES,
)
def restart_workload(workload: str, environment: str) -> CapabilityResult:
    """Return the outcome of the restart, or the reason it cannot be performed.

    The refusal names the action it refused. An approval request that was
    declined for an unnamed workload is a trace nobody can audit.
    """
    return CapabilityResult.failed(
        "restart_workload",
        CapabilityErrorClass.UNAVAILABLE,
        _NOT_YET_EXECUTABLE,
        detail=f"restart of {workload} in {environment}",
    )


@tool(
    name="rollback_release",
    display_name="Roll back a release",
    description=(
        "Return a workload to a previous release. Reversible by re-deploying the "
        "revision it is on now, which the rollback plan records first."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Rolling back changes what is running in production. It is reversible, but it "
        "moves every user onto different code while it is in effect."
    ),
    rollback_planner=ReleaseRollbackPlanner(),
    tags=("remediation", "rollback", "deploy"),
    use_cases=_ROLLBACK_USE_CASES,
)
def rollback_release(workload: str, environment: str, target_revision: str) -> CapabilityResult:
    """Return the outcome of the rollback, or the reason it cannot be performed."""
    return CapabilityResult.failed(
        "rollback_release",
        CapabilityErrorClass.UNAVAILABLE,
        _NOT_YET_EXECUTABLE,
        detail=f"rollback of {workload} in {environment} to {target_revision}",
    )


@tool(
    name="scale_workload",
    display_name="Scale a workload",
    description=(
        "Change a workload's replica count. Reversible by restoring the count recorded "
        "in the rollback plan before the change."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Scaling changes capacity and cost, and scaling down can turn a degradation into an outage."
    ),
    rollback_planner=ScaleRollbackPlanner(),
    tags=("remediation", "scale", "capacity"),
    use_cases=_SCALE_USE_CASES,
)
def scale_workload(workload: str, environment: str, replicas: int) -> CapabilityResult:
    """Return the outcome of the scale, or the reason it cannot be performed."""
    return CapabilityResult.failed(
        "scale_workload",
        CapabilityErrorClass.UNAVAILABLE,
        _NOT_YET_EXECUTABLE,
        detail=f"scale of {workload} in {environment} to {replicas} replica(s)",
    )
