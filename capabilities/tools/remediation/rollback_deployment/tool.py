"""Return a workload to a previous release."""

from __future__ import annotations

from capabilities.tools.remediation import _base
from capabilities.tools.remediation.rollback_deployment.rollback import ReleaseRollbackPlanner
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "rollback_deployment"

_USE_CASES = (
    "return a service to the previous release after a deploy correlates with the alert",
    "undo a configuration change identified as the trigger",
)


@tool(
    name=TOOL_NAME,
    display_name="Roll back a deployment",
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
    use_cases=_USE_CASES,
)
def rollback_deployment(workload: str, environment: str, target_revision: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        TOOL_NAME,
        detail=f"rollback of {workload} in {environment} to {target_revision}",
    )
