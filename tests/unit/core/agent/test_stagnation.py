"""The breaker that stops a loop spinning without waiting for the ceiling.

The iteration ceiling already bounds the worst case. What it does not do is
notice that the last four iterations achieved nothing — it will happily spend
the remaining sixteen finding out. The stagnation counter is what turns "it
terminates eventually" into "it stops when it stops learning".
"""

from __future__ import annotations

import pytest

from config.constants.investigation import MAX_STAGNANT_ITERATIONS
from core.agent.stagnation import observe

pytestmark = pytest.mark.unit


def test_a_productive_iteration_resets_the_counter() -> None:
    verdict = observe(2, produced_fresh_evidence=True)

    assert verdict.count == 0
    assert not verdict.stagnant
    assert not verdict.strip_tools
    assert verdict.nudge == ""


def test_a_sterile_iteration_increments_and_nudges() -> None:
    verdict = observe(0, produced_fresh_evidence=False)

    assert verdict.count == 1
    assert verdict.stagnant
    assert verdict.nudge


def test_the_nudge_says_how_many_iterations_are_left() -> None:
    verdict = observe(0, produced_fresh_evidence=False, threshold=3)

    assert "2" in verdict.nudge


def test_tool_access_is_stripped_at_the_threshold() -> None:
    verdict = observe(MAX_STAGNANT_ITERATIONS - 1, produced_fresh_evidence=False)

    assert verdict.count == MAX_STAGNANT_ITERATIONS
    assert verdict.strip_tools


def test_the_threshold_is_a_ceiling_the_caller_may_lower() -> None:
    verdict = observe(0, produced_fresh_evidence=False, threshold=1)

    assert verdict.strip_tools


def test_the_threshold_may_not_be_raised_above_the_constant() -> None:
    with pytest.raises(ValueError, match="threshold"):
        observe(0, produced_fresh_evidence=False, threshold=MAX_STAGNANT_ITERATIONS + 1)


def test_the_final_instruction_leaves_no_room_to_ask_for_another_call() -> None:
    from core.agent.stagnation import final_turn_instruction

    text = final_turn_instruction()

    assert "no" in text.lower()
    assert "answer" in text.lower()
