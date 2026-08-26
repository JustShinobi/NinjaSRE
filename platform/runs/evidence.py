"""How sure a run was, from what the run itself recorded.

Every console that shows an investigation eventually has to answer "and how much
of this should I believe". The tempting answer is a percentage, and it is the
wrong one: a number a model chooses about its own output is not a measurement,
and printing it beside real measurements makes the whole panel read as measured.

There is a real answer already in the trace. ``assess_evidence_sufficiency``
takes the conclusion, the evidence that supports it, and the evidence that is
still missing, *as arguments* — so the model's own account of what it could and
could not back is recorded verbatim, in the same place every other call is, and
this module does nothing but count it.

Three rules follow, and each is a decision rather than a detail.

**Silence is not zero.** A run that never called the capability said nothing
about its own evidence; a run that called it and found nothing missing said
something quite strong. Collapsing those two into "0 missing" would let the
first borrow the second's confidence, so ``assessed`` is on the value and every
caller has to look at it.

**A failed call is silence too.** The arguments survive a capability that
raised, and reading them anyway would report an assessment the run never
completed.

**The shape is never trusted.** These arguments are model output. Anything that
is not a list counts as nothing rather than as one, because a string counted by
``len`` would report "eleven pieces of evidence" for the word "three things".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from config.constants.investigation import (
    EVIDENCE_ASSESSMENT_CAPABILITY,
    EVIDENCE_MISSING_ARGUMENT,
    EVIDENCE_SUPPORTING_ARGUMENT,
)
from platform.persistence.ports.run_trace_store import ToolCallRecord, ToolCallStatus


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """What one run said about the evidence behind its own conclusion."""

    #: Whether the run completed an assessment at all. False is "it never said",
    #: never "it said nothing was backed".
    assessed: bool = False
    #: How many pieces of evidence the run named as supporting its conclusion.
    backed: int = 0
    #: How many it named as still missing.
    missing: int = 0

    @property
    def claims(self) -> int:
        """Return how many pieces of evidence the conclusion needed in total."""
        return self.backed + self.missing

    @property
    def sufficient(self) -> bool:
        """Return whether the run reached its conclusion with nothing outstanding."""
        return self.assessed and self.missing == 0


def _counted(value: object) -> int:
    """Return how many entries ``value`` holds, or nought when it is not a list.

    A string is deliberately not a sequence here. ``len("three things")`` is
    twelve, and twelve pieces of evidence is a worse answer than none.
    """
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def assessment_from_calls(calls: Sequence[ToolCallRecord]) -> EvidenceAssessment:
    """Return what ``calls`` say about the evidence behind the run's conclusion.

    The *last* completed assessment wins. A loop that assessed, gathered more,
    and assessed again concluded once — and it concluded at the end.
    """
    found = EvidenceAssessment()
    for call in calls:
        if call.tool_name != EVIDENCE_ASSESSMENT_CAPABILITY:
            continue
        if call.status is not ToolCallStatus.SUCCEEDED:
            continue
        found = EvidenceAssessment(
            assessed=True,
            backed=_counted(call.arguments.get(EVIDENCE_SUPPORTING_ARGUMENT)),
            missing=_counted(call.arguments.get(EVIDENCE_MISSING_ARGUMENT)),
        )
    return found


__all__ = ["EvidenceAssessment", "assessment_from_calls"]
