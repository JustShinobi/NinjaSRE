"""Recall of previous investigations — the contract now, the store later.

The episodic memory this reads from is a later feature. That is not a reason to
leave the tool out until then: its declaration is what the scorer, the reserve,
and the evaluation harness need in order to be built and measured against a
catalogue that has the shape the finished one will have.

What it must not do is pretend. A recall tool that quietly returned nothing
would look identical to a recall tool that searched and found nothing, and an
investigation would conclude "no similar incidents" on the strength of a store
that does not exist. So it returns an explicit unavailability, classified, with
the reason — which the loop can reason about and a reader can see in the trace.
"""

from __future__ import annotations

from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult

_RECALL_USE_CASES = (
    "find previous incidents with the same symptom on the same service",
    "check whether this alert has fired before and what resolved it",
    "recall which investigation strategy worked on this class of failure",
)

_RECALL_ANTI_EXAMPLES = ("looking up current system state, which a vendor tool reads directly",)

_UNAVAILABLE = (
    "Episodic memory is not configured for this deployment, so no previous "
    "investigation can be recalled. Treat this incident as unseen rather than "
    "as one with no precedent."
)


@tool(
    name="recall_similar_incidents",
    display_name="Recall similar incidents",
    description=(
        "Search previous investigations for incidents resembling this one, and return "
        "what was concluded and what resolved them. Use early, before gathering "
        "evidence a previous run already gathered."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.MEMORY,
    evidence_type=EvidenceType.INCIDENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("memory", "recall", "history"),
    use_cases=_RECALL_USE_CASES,
    anti_examples=_RECALL_ANTI_EXAMPLES,
)
def recall_similar_incidents(summary: str, limit: int = 5) -> CapabilityResult:
    """Return recalled incidents, or an explicit unavailability.

    Returning a classified result rather than an empty list is the whole point:
    "nothing found" and "nowhere to look" lead to different next moves, and only
    one of them is a finding.

    The detail carries what was asked for. A trace showing that recall was
    attempted, and with what, is worth more than one showing only that it was
    unavailable — the first says the investigation tried, the second does not.
    """
    return CapabilityResult.failed(
        "recall_similar_incidents",
        CapabilityErrorClass.UNAVAILABLE,
        _UNAVAILABLE,
        detail=f"searched for {summary!r}, up to {limit} result(s)",
    )
