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

**And a run that named nothing has not found nothing outstanding.** An
assessment with both lists empty is a call that said nothing, and it wore a
green "0 of 0 claims backed" on staging until this said otherwise.

Where to look for the two lists is not obvious and is the reason this shipped
wrong once. ``RunRecorder.record_call`` stores a call's own arguments *nested*
under an ``arguments`` key, beside the capability's ``result`` and the call's
timing — one JSONB body per call, so that the port keeps one bound rather than
two. A reader that took ``record.arguments["supporting_evidence"]`` therefore
found nothing on every run ever recorded, and reported every one of them as an
assessment that named nothing. All three shapes are read here: the nested
arguments, then the result (which carries the same two lists, and survives when
an oversized payload truncated the other half), then the flat body, for a
caller that records one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.investigation import (
    EVIDENCE_ASSESSMENT_CAPABILITY,
    EVIDENCE_MISSING_ARGUMENT,
    EVIDENCE_SUPPORTING_ARGUMENT,
)
from platform.persistence.ports.run_trace_store import ToolCallRecord, ToolCallStatus

#: Where ``RunRecorder.record_call`` puts a call's own arguments, and where it
#: puts what the capability returned. Both carry the two lists.
_NESTED_ARGUMENTS_KEY = "arguments"
_RESULT_KEY = "result"


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """What one run said about the evidence behind its own conclusion."""

    #: Whether the run completed an assessment at all. False is "it never said",
    #: never "it said nothing was backed".
    assessed: bool = False
    #: What the run named as supporting its conclusion, and what it named as
    #: still missing. Kept as the sentences rather than only as counts: a list
    #: of runs needs the number, and a reader who opened one wants the words,
    #: and deriving one from the other later would mean reading the trace twice.
    supporting: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()

    @property
    def backed(self) -> int:
        """Return how many pieces of evidence the run named as supporting it."""
        return len(self.supporting)

    @property
    def missing(self) -> int:
        """Return how many it named as still missing."""
        return len(self.missing_evidence)

    @property
    def claims(self) -> int:
        """Return how many pieces of evidence the conclusion needed in total."""
        return self.backed + self.missing

    @property
    def sufficient(self) -> bool:
        """Return whether the run backed its conclusion with nothing outstanding.

        ``backed`` has to be positive. An assessment naming neither supporting
        nor missing evidence is a call that said nothing, and reading it as
        "nothing is outstanding" is how a run that proved nothing wore the same
        green chip as a run that proved everything.
        """
        return self.assessed and self.backed > 0 and self.missing == 0


def _named(value: object) -> tuple[str, ...]:
    """Return the sentences ``value`` holds, or nothing when it is not a list.

    A string is deliberately not a sequence here. Iterating ``"three things"``
    would report twelve pieces of evidence, one per character, and twelve is a
    worse answer than none. An entry inside the list that is not a sentence is
    dropped rather than stringified, so the count and the names agree.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(entry for entry in value if isinstance(entry, str) and entry != "")


def _bodies(stored: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return the places the two lists may be, in the order they are trusted."""
    found: list[Mapping[str, Any]] = []
    for key in (_NESTED_ARGUMENTS_KEY, _RESULT_KEY):
        held = stored.get(key)
        if isinstance(held, Mapping):
            found.append(held)
    found.append(stored)
    return tuple(found)


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
        supporting: tuple[str, ...] = ()
        missing: tuple[str, ...] = ()
        for body in _bodies(call.arguments):
            supporting = _named(body.get(EVIDENCE_SUPPORTING_ARGUMENT))
            missing = _named(body.get(EVIDENCE_MISSING_ARGUMENT))
            if supporting or missing:
                break
        found = EvidenceAssessment(assessed=True, supporting=supporting, missing_evidence=missing)
    return found


__all__ = ["EvidenceAssessment", "assessment_from_calls"]
