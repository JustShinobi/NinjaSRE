"""Change what a workload is allowed to consume."""

from __future__ import annotations

from capabilities.tools.remediation import _base
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "update_resource_limits"

_USE_CASES = (
    "raise a memory limit for a workload the kernel is killing under normal load",
    "restore a limit lowered during an earlier cost exercise",
)

_ANTI_EXAMPLES = (
    "raising a limit to hide a leak, which delays the failure rather than fixing it",
    "lowering a limit during an incident, which is a second change nobody asked for",
)


@tool(
    name=TOOL_NAME,
    display_name="Update resource limits",
    description=(
        "Change a workload's CPU and memory requests and limits. Reversible by "
        "restoring the values recorded in the rollback plan before the change."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    # Reversible by setting them back, and it restarts the workload's instances to
    # take effect, which is a further action to undo and an interruption to cause.
    risk_class="moderate",
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Changing limits restarts the workload on most control planes, and a limit "
        "set below current usage turns a slow degradation into an immediate kill."
    ),
    rollback_plan=(
        "Restore every request and limit the workload had before the change, not "
        "only the field that was edited."
    ),
    tags=("remediation", "resources", "limits", "memory", "cpu"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
def update_resource_limits(
    workload: str,
    environment: str,
    cpu_request: str = "",
    cpu_limit: str = "",
    memory_request: str = "",
    memory_limit: str = "",
) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate.

    The detail spells out every field the call named. "A limit change to
    checkout-api" is not something an approver or an auditor can act on; the
    fields and their values are.
    """
    named = ", ".join(
        f"{name}={value}"
        for name, value in (
            ("cpu_request", cpu_request),
            ("cpu_limit", cpu_limit),
            ("memory_request", memory_request),
            ("memory_limit", memory_limit),
        )
        if value
    )
    return _base.refuse(
        TOOL_NAME,
        detail=f"limit change to {workload} in {environment}: {named or 'no field named'}",
    )
