"""Comparing a produced category against the one an answer key expected.

The evaluation suite needs one question answered — did this run get the
category right — and it needs the answer to be the same question every time.
Putting the comparison here rather than in the suite is what stops "close
enough" from being redefined the next time a scenario fails.

Two categories are *aligned* when they are equal, and nothing else. There is no
partial credit: ``capacity_limit`` and ``resource_exhaustion`` are neighbouring
answers with opposite remediations, and scoring them as a near-miss would
reward a diagnosis that sends an operator to add replicas when the fix is a
memory leak.

What the module does offer is the neighbouring set, for a report that wants to
say *how* a run was wrong. That is presentation, and it is kept separate from
scoring on purpose.
"""

from __future__ import annotations

from typing import Final

from core.domain.diagnosis.taxonomy import RootCauseCategory

#: Categories an investigation confuses with each other often enough to be worth
#: naming in a report. Symmetric by construction below, and never consulted by
#: scoring: this is for the sentence that says which way a run went wrong.
_NEIGHBOURS: Final[tuple[frozenset[RootCauseCategory], ...]] = (
    frozenset({RootCauseCategory.RESOURCE_EXHAUSTION, RootCauseCategory.CAPACITY_LIMIT}),
    frozenset({RootCauseCategory.CODE_DEFECT, RootCauseCategory.DEPLOYMENT_REGRESSION}),
    frozenset({RootCauseCategory.CONFIGURATION_ERROR, RootCauseCategory.DEPLOYMENT_REGRESSION}),
    frozenset({RootCauseCategory.DEPENDENCY_FAILURE, RootCauseCategory.EXTERNAL_PROVIDER}),
    frozenset({RootCauseCategory.NETWORK_FAILURE, RootCauseCategory.INFRASTRUCTURE_FAILURE}),
    frozenset({RootCauseCategory.HEALTHY, RootCauseCategory.SCHEDULED_MAINTENANCE}),
)


def aligned(produced: RootCauseCategory, expected: RootCauseCategory) -> bool:
    """Return whether ``produced`` is the category ``expected`` names.

    Equality, deliberately. Partial credit for a neighbouring category would
    reward a diagnosis whose remediation sends an operator the wrong way.
    """
    return produced is expected


def neighbours_of(category: RootCauseCategory) -> tuple[RootCauseCategory, ...]:
    """Return the categories commonly confused with ``category``, in taxonomy order."""
    related: set[RootCauseCategory] = set()
    for group in _NEIGHBOURS:
        if category in group:
            related |= group
    related.discard(category)
    return tuple(member for member in RootCauseCategory if member in related)


def misalignment_note(produced: RootCauseCategory, expected: RootCauseCategory) -> str:
    """Return one sentence describing how ``produced`` differs from ``expected``."""
    if aligned(produced, expected):
        return ""
    if produced in neighbours_of(expected):
        return (
            f"answered {produced.value!r} where the key says {expected.value!r} — "
            "a commonly confused pair whose remediations differ"
        )
    if produced is RootCauseCategory.UNKNOWN:
        return f"attributed no cause where the key says {expected.value!r}"
    return f"answered {produced.value!r} where the key says {expected.value!r}"


__all__ = [
    "aligned",
    "misalignment_note",
    "neighbours_of",
]
