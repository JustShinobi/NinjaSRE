"""Change a workload's replica count."""

from __future__ import annotations

from capabilities.tools.remediation import _base
from capabilities.tools.remediation.scale_workload.rollback import ScaleRollbackPlanner
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "scale_workload"

_USE_CASES = (
    "add capacity to a workload saturating its current replicas",
    "reduce a replica count raised during an earlier incident",
)


@tool(
    name=TOOL_NAME,
    display_name="Scale a workload",
    description=(
        "Change a workload's replica count. Reversible by restoring the count recorded "
        "in the rollback plan before the change."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    # Reversible by scaling back, reaches the one workload named, and the worst
    # case is a period of too little capacity.
    risk_class="low",
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Scaling changes capacity and cost, and scaling down can turn a degradation into an outage."
    ),
    rollback_planner=ScaleRollbackPlanner(),
    tags=("remediation", "scale", "capacity"),
    use_cases=_USE_CASES,
)
def scale_workload(workload: str, environment: str, replicas: int) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        TOOL_NAME,
        detail=f"scale of {workload} in {environment} to {replicas} replica(s)",
    )
