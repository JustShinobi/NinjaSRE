"""Article I, as a function: a claim is validated only if the run holds its evidence.

This is the check the whole system exists around. A model that writes "the pod
was OOM-killed [e7]" when the run holds no ``e7`` has produced a sentence that
reads exactly like a finding and is a hypothesis. Demotion is what keeps the
two distinguishable, and it happens against the evidence in state rather than
against the model's own account of its citations.

Demotion, not deletion. An unbacked claim is often the most interesting thing
in the report — it is what the investigation believed and could not show — and
dropping it would leave the next investigation to rediscover the same hunch.
The report renders it under a different heading; it does not lose it.
"""

from __future__ import annotations

from dataclasses import replace

from core.domain.diagnosis.result import Claim, Diagnosis, split_claims
from core.state.slices import EvidenceSlice


def validate(diagnosis: Diagnosis, evidence: EvidenceSlice) -> Diagnosis:
    """Return ``diagnosis`` with every unbacked claim moved to ``non_validated``.

    Claims the model already put in ``non_validated_claims`` are re-checked
    too. A claim can only move one way — an unbacked claim is never promoted —
    but a model that filed a well-supported claim as unvalidated should not
    have its report understate what it established.
    """
    held = evidence.ids
    backed, unbacked = split_claims(diagnosis.claims, held)
    return replace(diagnosis, validated_claims=backed, non_validated_claims=unbacked)


def unbacked_citations(diagnosis: Diagnosis, evidence: EvidenceSlice) -> tuple[str, ...]:
    """Return every evidence identifier the diagnosis cited that the run does not hold.

    Not used to change the diagnosis — validation has already demoted the
    claims — but recorded, because an invented identifier is a specific failure
    worth counting separately from a claim that cited nothing at all.
    """
    held = evidence.ids
    return tuple(
        sorted(
            {
                evidence_id
                for claim in diagnosis.claims
                for evidence_id in claim.evidence_ids
                if evidence_id not in held
            }
        )
    )


def uncited_evidence(diagnosis: Diagnosis, evidence: EvidenceSlice) -> tuple[str, ...]:
    """Return the entries the run gathered that no claim rested on.

    A high count is the signal that the loop spent its budget on observations
    the conclusion never used, which is a different problem from a wrong
    diagnosis and is invisible without this.
    """
    cited = {evidence_id for claim in diagnosis.claims for evidence_id in claim.evidence_ids}
    return tuple(entry.id for entry in evidence.entries if entry.id not in cited)


def is_evidence_backed(claim: Claim, evidence: EvidenceSlice) -> bool:
    """Return whether ``claim`` cites at least one entry the run holds."""
    return claim.backed_by(evidence.ids)


__all__ = [
    "is_evidence_backed",
    "unbacked_citations",
    "uncited_evidence",
    "validate",
]
