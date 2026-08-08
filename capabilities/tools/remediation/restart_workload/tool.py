"""Restart a workload's instances — the action that most often hides its cause.

Declared above ``read_sensitive``, so the metadata type enforces what that
means: approval is required, the reason a human is being asked is written
down, and a plan exists before the action rather than after it.
"""

from __future__ import annotations

from capabilities.tools.remediation import _base
from capabilities.tools.remediation.restart_workload.rollback import RestartRollbackPlanner
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "restart_workload"

_USE_CASES = (
    "clear a workload stuck in a state a restart resolves, after the cause is known",
    "recover a service whose connection pool has become unusable",
)

_ANTI_EXAMPLES = (
    "restarting before the cause is understood, which destroys the evidence",
    "restarting a workload whose failure will recur immediately",
)


@tool(
    name=TOOL_NAME,
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
    # Undone only by waiting, and it destroys process state and in-flight requests
    # on the way — which is one workload's worth of damage, not an estate's.
    risk_class="moderate",
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Restarting drops every in-flight request and destroys the process state that "
        "would explain the failure. Neither is recoverable."
    ),
    rollback_planner=RestartRollbackPlanner(),
    tags=("remediation", "restart", "workload"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
def restart_workload(workload: str, environment: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(TOOL_NAME, detail=f"restart of {workload} in {environment}")
