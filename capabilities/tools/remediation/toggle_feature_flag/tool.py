"""Turn a feature flag on or off, or move its rollout."""

from __future__ import annotations

from capabilities.tools.remediation import _base
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "toggle_feature_flag"

_USE_CASES = (
    "turn off a flag whose rollout correlates with the onset of the symptom",
    "reduce a rollout percentage while the cause is established",
)

_ANTI_EXAMPLES = (
    "toggling flags one at a time to see which helps, which is a change per attempt",
    "turning a flag on as a mitigation, which is a launch nobody reviewed",
)


@tool(
    name=TOOL_NAME,
    display_name="Toggle a feature flag",
    description=(
        "Change a feature flag's value or rollout percentage. Reversible by restoring "
        "both, which the rollback plan records before the change."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "A flag changes behaviour for real users immediately and without a deploy, "
        "which is what makes it the fastest mitigation and the easiest to get wrong."
    ),
    rollback_plan=(
        "Restore the flag's previous value and its previous rollout percentage. "
        "Restoring the value alone would turn a partial rollout into a full one."
    ),
    tags=("remediation", "feature-flag", "rollout"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
def toggle_feature_flag(
    flag: str, environment: str, enabled: bool, rollout: str = ""
) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate.

    The detail names the rollout as well as the value. An audit line saying a
    flag was enabled, without saying for how much of the traffic, describes two
    very different changes identically.
    """
    state = "enabled" if enabled else "disabled"
    at = f" at a {rollout} rollout" if rollout else ""
    return _base.refuse(TOOL_NAME, detail=f"set {flag} in {environment} to {state}{at}")
