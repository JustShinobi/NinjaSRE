"""What the attempt cost, reported always and gated apart from correctness.

Cost is the axis that catches the change nothing else does: a release that
improves accuracy by two points and triples the token bill is a real trade-off
somebody should decide on, and a suite that only reported correctness would pass
it silently. Equally, a cost rise with *no* accuracy change is a regression on
its own terms, which is SC-006 and the reason the gate downstream keeps this
axis in its own bucket.

The budget widens with difficulty. Holding a level-four incident to a level-one
budget would fail every hard scenario on cost and leave the axis reporting the
curriculum rather than the agent. The numbers are bounds in
``config/constants/`` like every other bound, and they are deliberately generous:
this axis exists to catch an investigation that has started looping, not to
police a slow laptop.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.evaluation import (
    AXIS_COST,
    SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY,
    SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY,
)
from tests.harness.scoring.axes.result import AxisScore


@dataclass(frozen=True, slots=True)
class CostBudget:
    """What one attempt at one scenario is allowed to spend."""

    tokens: int
    seconds: float

    @classmethod
    def for_difficulty(cls, difficulty: int) -> CostBudget:
        """Return the budget for a scenario at ``difficulty``.

        An unrecognised level falls back to the widest budget rather than the
        narrowest. A curriculum that grew a fifth rung should not report a
        corpus-wide cost regression on the day it did.
        """
        return cls(
            tokens=SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY.get(
                difficulty, max(SCENARIO_TOKEN_BUDGET_BY_DIFFICULTY.values())
            ),
            seconds=SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY.get(
                difficulty, max(SCENARIO_SECONDS_BUDGET_BY_DIFFICULTY.values())
            ),
        )


def score_cost(budget: CostBudget, *, tokens: int, seconds: float) -> AxisScore:
    """Return whether the attempt stayed inside ``budget``, on both counts."""
    over_tokens = tokens > budget.tokens
    over_clock = seconds > budget.seconds

    if over_tokens and over_clock:
        detail = f"{tokens} tokens against {budget.tokens}, and {seconds:.1f}s against {budget.seconds:.1f}s"
    elif over_tokens:
        detail = f"{tokens} tokens against a budget of {budget.tokens}"
    elif over_clock:
        detail = f"{seconds:.1f}s against a budget of {budget.seconds:.1f}s"
    else:
        detail = f"{tokens} tokens and {seconds:.1f}s, both inside budget"

    return AxisScore(
        name=AXIS_COST,
        passed=not (over_tokens or over_clock),
        expected=(str(budget.tokens), f"{budget.seconds:.1f}s"),
        observed=(str(tokens), f"{seconds:.1f}s"),
        measurements={
            "tokens": float(tokens),
            "seconds": float(seconds),
            "token_budget": float(budget.tokens),
            "seconds_budget": float(budget.seconds),
        },
        detail=detail,
    )


__all__ = ["CostBudget", "score_cost"]
