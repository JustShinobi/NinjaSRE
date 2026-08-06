"""Empty a cache — the action whose rollback plan does not exist.

Declared ``write_irreversible`` with a rollback plan that says so in words.
The metadata type accepts a declared plan or a planner, and what is declared
here is the truth: there is no undo, and an approver is being asked to accept
that rather than to trust one exists.
"""

from __future__ import annotations

from capabilities.tools.remediation import _base
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityResult

TOOL_NAME = "clear_cache"

_USE_CASES = (
    "clear a cache holding a value a deploy has since made wrong",
    "empty a cache whose corruption is established as the cause",
)

_ANTI_EXAMPLES = (
    "clearing a cache to see whether it helps, which is an irreversible experiment",
    "clearing during peak load, which sends every miss to the origin at once",
)


@tool(
    name=TOOL_NAME,
    display_name="Clear a cache",
    description=(
        "Empty a cache, or one namespace within it. There is no rollback: the entries "
        "are gone and only traffic repopulates them, so every miss goes to the origin "
        "until it does."
    ),
    domain="remediation",
    evidence_source="control_plane",
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "A cleared cache cannot be restored, and every request that would have hit it "
        "goes to the origin until traffic refills it. On a busy service that is a "
        "second incident."
    ),
    rollback_plan=(
        "There is none. A cleared cache is repopulated by traffic and by nothing "
        "else, so approving this is accepting the origin load until it is warm again."
    ),
    tags=("remediation", "cache", "irreversible"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
def clear_cache(cache: str, environment: str, namespace: str = "") -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    where = f"{cache}/{namespace}" if namespace else cache
    return _base.refuse(TOOL_NAME, detail=f"clear of {where} in {environment}")
