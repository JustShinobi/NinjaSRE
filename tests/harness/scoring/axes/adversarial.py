"""Were the planted confounders dismissed, or merely not mentioned.

This axis is separate from accuracy for one reason, and it is the reason the
whole five-axis split exists: an agent that is right when the evidence is clean
and right-by-luck when it is not has a specific weakness, and a single accuracy
number hides it completely.

A scenario at difficulty two or above plants a confounder — a coincident deploy,
a louder secondary symptom, a dependency that had already recovered — and its
answer key names the words a diagnosis has to use to show it looked at the thing
and set it aside. Silence is not resistance. An investigation that never
mentioned the deploy might have ruled it out and might never have seen it, and
from the outside those are indistinguishable, so the axis scores them the same.

Where no confounder was planted the axis is inapplicable, not passed. A suite
whose adversarial number was mostly level-one scenarios would read as resistance
the corpus never tested.
"""

from __future__ import annotations

from config.constants.evaluation import AXIS_ADVERSARIAL
from tests.harness.loader import AnswerKey
from tests.harness.scoring.axes.result import AxisScore, contains_all, not_asserted


def score_adversarial(answer: AnswerKey, *, said: str) -> AxisScore:
    """Return whether every confounder this key names was explicitly dismissed."""
    if not answer.ruling_out_keywords:
        return not_asserted(
            AXIS_ADVERSARIAL,
            detail="this answer key plants no confounder to resist",
        )

    dismissed, silent = contains_all(said, answer.ruling_out_keywords)
    return AxisScore(
        name=AXIS_ADVERSARIAL,
        passed=not silent,
        expected=answer.ruling_out_keywords,
        observed=dismissed,
        missing=silent,
        measurements={
            "dismissed": float(len(dismissed)),
            "planted": float(len(answer.ruling_out_keywords)),
        },
        detail=(
            "every planted confounder was named and set aside"
            if not silent
            else "the diagnosis never mentions these, so it cannot be said to have ruled them out"
        ),
    )


__all__ = ["score_adversarial"]
