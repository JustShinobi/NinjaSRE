"""Stop a node accepting work, and optionally move what is already on it."""

from __future__ import annotations

from capabilities.tools.remediation import _base
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, RollbackPlan, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "cordon_drain_node"

_USE_CASES = (
    "take a node with failing hardware out of service before it takes workloads with it",
    "stop new work landing on a node while its disk pressure is investigated",
)

_ANTI_EXAMPLES = (
    "cordoning the last healthy node in a pool, which has nowhere to reschedule to",
    "draining during a capacity shortage, which moves the outage rather than fixing it",
)


@tool(
    name=TOOL_NAME,
    display_name="Cordon or drain a node",
    description=(
        "Stop a node accepting new work, and optionally evict what is running on it. "
        "Reversible by uncordoning; the evicted workloads stay where they rescheduled."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "Cordoning removes capacity from the pool, and draining moves running "
        "workloads. In a pool with little headroom the two together are an outage."
    ),
    rollback_plan=(
        "Uncordon the node. Workloads that were drained stay where they were "
        "rescheduled — moving them back is a second disruption for no benefit."
    ),
    tags=("remediation", "node", "cordon", "drain"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
def cordon_drain_node(node: str, environment: str, drain: bool = False) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    what = "cordon and drain" if drain else "cordon"
    return _base.refuse(TOOL_NAME, detail=f"{what} of {node} in {environment}")


#: Re-exported so the declaration's static plan and the generated one stay
#: readable side by side in a review.
__all__ = ["TOOL_NAME", "RollbackPlan", "cordon_drain_node"]
