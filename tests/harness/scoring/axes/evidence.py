"""Did the conclusion rest on anything, and on anything the run actually holds.

Article I is one sentence — every claim names its evidence — and this axis is
the only place in the product where that sentence is checked against a number
rather than trusted to a prompt. It has two halves and both are load-bearing.

**The sources were reached.** An answer key naming ``required_evidence_sources``
is saying that a diagnosis of this incident which never looked at Prometheus is
a guess that happened to land. Checking the sources the run *collected* rather
than the ones it was offered is what makes that a fact.

**The claims cite entries that exist.** The diagnosis stage already splits
claims into validated and non-validated by whether their cited identifiers are
among the ones the run holds. This axis re-checks that split rather than
trusting the labels, because a corpus of stored diagnoses is exactly where a
hand-edited or replayed record would get to claim its own validation.

An invented citation is not a partial success. It is a claim with nothing behind
it plus a fabricated reference, which is worse than an honest hypothesis.
"""

from __future__ import annotations

from collections.abc import Sequence

from config.constants.evaluation import AXIS_EVIDENCE
from core.domain.diagnosis.result import Claim
from tests.harness.loader import AnswerKey
from tests.harness.scoring.axes.result import AxisScore, not_asserted


def score_evidence(
    answer: AnswerKey,
    *,
    sources: Sequence[str],
    claims: Sequence[Claim],
    held: frozenset[str],
) -> AxisScore:
    """Return whether the required sources were collected and the claims are backed.

    ``claims`` are the ones the diagnosis filed as validated; ``held`` are the
    evidence identifiers the run actually carries.
    """
    if not answer.required_evidence_sources and not claims:
        return not_asserted(
            AXIS_EVIDENCE,
            detail="this answer key requires no source and the diagnosis made no validated claim",
        )

    collected = tuple(dict.fromkeys(sources))
    absent = tuple(name for name in answer.required_evidence_sources if name not in collected)
    unbacked = tuple(claim.statement for claim in claims if not claim.backed_by(held))

    passed = not absent and not unbacked
    if absent and unbacked:
        detail = (
            "a required source was never reached, and a claim cites an entry the run does not hold"
        )
    elif absent:
        detail = "the conclusion does not rest on evidence this scenario says it has to rest on"
    elif unbacked:
        detail = "a validated claim cites an evidence identifier this run never produced"
    else:
        detail = "every required source was collected and every validated claim is backed"

    return AxisScore(
        name=AXIS_EVIDENCE,
        passed=passed,
        expected=answer.required_evidence_sources,
        observed=collected,
        missing=absent,
        unexpected=unbacked,
        measurements={
            "sources_collected": float(len(collected)),
            "claims_checked": float(len(claims)),
            "claims_unbacked": float(len(unbacked)),
        },
        detail=detail,
    )


__all__ = ["score_evidence"]
