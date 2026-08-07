"""How the agent got there: distance, wandering, looping, and the loop ceiling.

Four measurements, one axis, and they are one axis because they answer one
question — was this investigation *efficient* — while the pass rule needs all
four. An agent inside the edit distance that called the same endpoint six times
is not efficient, and one that took the golden path in eleven loops when the key
allows six is not either.

The distance number is the one worth watching over time. It is reported under
every matching mode, including the modes that do not gate on it, because a
``set``-matched scenario whose distance has climbed for three releases is about
to fail and the mode it was scored under should not be what hides that.

``deviated`` exists for FR-011. An investigation that reached the correct root
cause by a shorter route is not wrong; it took a different route, which is a
trajectory finding and belongs in this axis's detail rather than in the accuracy
axis's verdict. Whether the deviation is *acceptable* is what the answer key's
``max_edit_distance`` says, and that is a decision its author made in writing.
"""

from __future__ import annotations

from collections.abc import Sequence

from config.constants.evaluation import AXIS_TRAJECTORY
from config.constants.investigation import MAX_INVESTIGATION_LOOPS
from tests.harness.loader import AnswerKey
from tests.harness.scoring.axes.result import AxisScore, not_asserted
from tests.harness.scoring.matching import Step, compare, steps_of


def score_trajectory(
    answer: AnswerKey, *, trajectory: Sequence[Step], iterations: int
) -> AxisScore:
    """Return how far the route was from the golden one, and what it wasted.

    Falls back to ``optimal_trajectory`` — the order-free field older answer keys
    carry — when no golden trajectory is declared, so a key written before the
    matching modes existed still scores on this axis rather than vanishing from
    it.
    """
    golden = answer.golden_trajectory
    if golden is None and not answer.optimal_trajectory:
        return _loops_only(answer, iterations=iterations, trajectory=trajectory)

    if golden is not None:
        expected = steps_of(golden.ordered_actions)
        mode = golden.matching
        allowance = golden.max_edit_distance
        max_extra: int | None = golden.max_extra_actions
        max_redundant: int | None = golden.max_redundancy
    else:
        # An older key declares the actions and nothing about order or waste.
        # Scoring it as though it had asked for zero extras would fail every
        # scenario in the shipped corpus on an assertion nobody wrote.
        expected = steps_of(answer.optimal_trajectory)
        mode = "set"
        allowance = 0
        max_extra = None
        max_redundant = None

    match = compare(expected, trajectory, mode=mode, max_edit_distance=allowance)
    ceiling = answer.max_investigation_loops or MAX_INVESTIGATION_LOOPS

    too_much_wandering = max_extra is not None and len(match.extra_actions) > max_extra
    too_much_repetition = max_redundant is not None and len(match.redundant_calls) > max_redundant
    over_ceiling = iterations > ceiling

    if not match.within_distance:
        detail = (
            f"{match.mode} matching: distance {match.distance} against an allowance of {allowance}"
        )
        if match.deviated and not match.missing:
            detail += "; the golden actions were all taken, in another order"
    elif too_much_wandering:
        detail = f"{len(match.extra_actions)} actions beyond the golden path, at most {max_extra}"
    elif too_much_repetition:
        detail = f"{len(match.redundant_calls)} repeated calls, at most {max_redundant}"
    elif over_ceiling:
        detail = f"{iterations} loop iterations against this answer key's ceiling of {ceiling}"
    elif match.deviated:
        detail = (
            f"a different route to the same place: distance {match.distance}, inside the "
            f"allowance of {allowance}"
        )
    else:
        detail = "the golden trajectory, within every bound the answer key sets"

    return AxisScore(
        name=AXIS_TRAJECTORY,
        passed=not (
            not match.within_distance or too_much_wandering or too_much_repetition or over_ceiling
        ),
        expected=match.golden,
        observed=match.observed,
        missing=match.missing,
        unexpected=match.extra_actions,
        measurements={
            "distance": float(match.distance),
            "max_edit_distance": float(allowance),
            "extra_actions": float(len(match.extra_actions)),
            "redundant_calls": float(len(match.redundant_calls)),
            "iterations": float(iterations),
            "max_investigation_loops": float(ceiling),
            "deviated": 1.0 if match.deviated else 0.0,
        },
        detail=detail,
    )


def _loops_only(answer: AnswerKey, *, iterations: int, trajectory: Sequence[Step]) -> AxisScore:
    """Return the axis for a key that declares no expected route at all.

    Still a measurement rather than an abstention, because Article II's loop
    bound applies to every investigation whether or not somebody wrote down what
    the ideal one looks like. Only the *comparison* is inapplicable.
    """
    from tests.harness.scoring.matching import flatten

    ceiling = answer.max_investigation_loops
    observed = flatten(trajectory)
    if ceiling is None:
        return not_asserted(
            AXIS_TRAJECTORY,
            detail="this answer key declares neither a golden trajectory nor a loop ceiling",
        )

    return AxisScore(
        name=AXIS_TRAJECTORY,
        passed=iterations <= ceiling,
        expected=(f"at most {ceiling} loops",),
        observed=observed,
        measurements={"iterations": float(iterations), "max_investigation_loops": float(ceiling)},
        detail=(
            f"no golden trajectory is declared; {iterations} loop iterations against a "
            f"ceiling of {ceiling}"
        ),
    )


__all__ = ["score_trajectory"]
