"""Making the model's reasoning a recorded step rather than a paragraph of prose.

A hypothesis stated inside a text response is invisible to everything: the
trace cannot count how many were raised, the evaluation suite cannot tell a run
that considered three explanations from one that committed to the first, and a
human reading the report cannot see what was ruled out.

Making it a tool call fixes all three at once, for the cost of one schema. The
hypothesis becomes a structured record with the evidence behind it and the step
that would confirm or kill it, and Article I's rule — a conclusion carries the
observations that support it — becomes something the framework can check rather
than something a prompt asks for.

This is also the reserve's justification made concrete. The reserved slots
exist so that this tool is present on the turn where an investigation has
twenty vendor tools and no idea what is happening.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel

_HYPOTHESIS_USE_CASES = (
    "state what you believe is happening before gathering more evidence",
    "record an explanation you have ruled out, so it is not investigated twice",
    "commit to the next observation that would distinguish two explanations",
)

_HYPOTHESIS_ANTI_EXAMPLES = (
    "reporting a conclusion that is already supported by gathered evidence",
    "narrating what a tool call is about to do",
)

_ASSESSMENT_USE_CASES = (
    "decide whether the evidence gathered so far supports a conclusion",
    "identify which kind of evidence is missing before concluding",
)


@tool(
    name="record_hypothesis",
    display_name="Record a hypothesis",
    description=(
        "State a candidate explanation, the evidence that suggests it, and the single "
        "next observation that would confirm or eliminate it. Use before gathering "
        "more evidence, so the investigation is directed rather than exploratory."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.REASONING,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("reasoning", "methodology", "hypothesis"),
    use_cases=_HYPOTHESIS_USE_CASES,
    anti_examples=_HYPOTHESIS_ANTI_EXAMPLES,
)
def record_hypothesis(
    hypothesis: str,
    supporting_evidence: list[str],
    next_observation: str,
    confidence: str = "medium",
) -> dict[str, Any]:
    """Return the hypothesis as a structured record for the trace.

    Nothing is computed. The value is that the reasoning becomes a countable,
    reviewable step instead of a sentence buried in a response.
    """
    return {
        "hypothesis": hypothesis,
        "supporting_evidence": supporting_evidence,
        "next_observation": next_observation,
        "confidence": confidence,
    }


@tool(
    name="assess_evidence_sufficiency",
    display_name="Assess evidence sufficiency",
    description=(
        "Judge whether the evidence gathered so far supports a conclusion, and name "
        "what kind of evidence is missing if it does not. Use before concluding."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.REASONING,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("reasoning", "methodology", "evidence"),
    use_cases=_ASSESSMENT_USE_CASES,
)
def assess_evidence_sufficiency(
    conclusion: str,
    supporting_evidence: list[str],
    missing_evidence: list[str],
) -> dict[str, Any]:
    """Return the assessment, including whether anything is still missing."""
    return {
        "conclusion": conclusion,
        "supporting_evidence": supporting_evidence,
        "missing_evidence": missing_evidence,
        "sufficient": not missing_evidence,
    }
