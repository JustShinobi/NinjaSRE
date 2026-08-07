"""Did the investigation reach the right conclusion, on four counts at once.

The four are not variations on one check. A category is a claim about *what kind
of thing* went wrong and is compared against a closed taxonomy; keywords are a
claim about what the diagnosis actually said; and the two forbidden lists are
the ones that make the axis adversarial rather than generous.

Forbidden categories are the interesting half. A scenario that plants a
misleading deployment alongside a real memory limit has one correct answer and
one *attractive* wrong one, and an agent that names the attractive wrong one
will still use the word "memory" somewhere in three paragraphs of prose. So a
forbidden category fails the axis outright, whatever the keyword check says —
which is acceptance scenario 3 and the reason it is a scenario at all.
"""

from __future__ import annotations

from config.constants.evaluation import AXIS_ACCURACY
from tests.harness.loader import AnswerKey
from tests.harness.scoring.axes.result import AxisScore, contains_all


def score_accuracy(answer: AnswerKey, *, category: str, said: str) -> AxisScore:
    """Return whether the conclusion was right, and on which count it was not.

    ``said`` is everything the agent said — conclusion, diagnosis, causal chain,
    remediation, claims. A keyword used only in a recommended action still shows
    the agent identified the thing, and a check that could only see the summary
    would score that as a miss.
    """
    accepted = answer.accepted_categories
    forbidden = tuple(name for name in answer.forbidden_categories if name == category)
    present, absent = contains_all(said, answer.required_keywords)
    banned, _ = contains_all(said, answer.forbidden_keywords)

    if forbidden:
        return AxisScore(
            name=AXIS_ACCURACY,
            passed=False,
            expected=tuple(sorted(accepted)),
            observed=(category,),
            unexpected=forbidden,
            detail=(
                f"{category!r} is a forbidden category for this scenario: the required "
                f"keywords being present does not make an attribution to it correct"
            ),
        )

    if category not in accepted:
        return AxisScore(
            name=AXIS_ACCURACY,
            passed=False,
            expected=tuple(sorted(accepted)),
            observed=(category,),
            unexpected=(category,),
            detail="the category is outside the set this answer key accepts",
        )

    if absent:
        return AxisScore(
            name=AXIS_ACCURACY,
            passed=False,
            expected=answer.required_keywords,
            observed=present,
            missing=absent,
            detail="the category was right and the diagnosis did not say what it had to say",
        )

    if banned:
        return AxisScore(
            name=AXIS_ACCURACY,
            passed=False,
            expected=answer.forbidden_keywords,
            observed=(category,),
            unexpected=banned,
            detail="the diagnosis asserted something this scenario's evidence rules out",
        )

    return AxisScore(
        name=AXIS_ACCURACY,
        passed=True,
        expected=tuple(sorted(accepted)),
        observed=(category,),
        detail="the category is accepted, every required keyword is present, nothing forbidden is",
    )


__all__ = ["score_accuracy"]
