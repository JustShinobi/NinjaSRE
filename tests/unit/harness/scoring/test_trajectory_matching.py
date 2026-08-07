"""The three matching modes, and what each one is willing to forgive.

The example in the plan is the whole specification in four lines, so it is the
first test here and it is written exactly as the plan writes it: the same golden
path, the same actual path, and the three verdicts that follow. If those three
ever disagree with the plan, this file is where it shows.

Everything else is the part the example does not reach — parallel batches,
redundant calls counted apart from extra ones, and the trajectory that gets the
right answer by a route nobody wrote down.
"""

from __future__ import annotations

import pytest

from tests.harness.scoring.matching import (
    LCS,
    SET,
    STRICT,
    Step,
    UnknownMatchingMode,
    compare,
    normalise_mode,
    steps_from_iterations,
    steps_of,
)

pytestmark = pytest.mark.unit

#: The plan's worked example, verbatim.
GOLDEN = ("list_pods", "get_events", "get_pod_logs")
ACTUAL = ("list_pods", "get_metrics", "get_events", "get_pod_logs")


def test_strict_rejects_the_sequence_the_agent_interrupted() -> None:
    """One insertion in the middle is a different sequence, and strict says so."""
    match = compare(steps_of(GOLDEN), steps_of(ACTUAL), mode=STRICT)

    assert not match.within_distance
    assert match.mode == STRICT


def test_lcs_scores_one_insertion_as_a_distance_of_one() -> None:
    """The plan's number: distance 1, and it passes once one is allowed."""
    match = compare(steps_of(GOLDEN), steps_of(ACTUAL), mode=LCS, max_edit_distance=1)

    assert match.distance == 1
    assert match.within_distance
    assert match.missing == ()


def test_lcs_fails_the_same_trajectory_when_no_distance_is_allowed() -> None:
    """``max_edit_distance`` is the knob, and zero is the strictest setting of it."""
    match = compare(steps_of(GOLDEN), steps_of(ACTUAL), mode=LCS, max_edit_distance=0)

    assert match.distance == 1
    assert not match.within_distance


def test_set_ignores_order_entirely() -> None:
    """Membership, and nothing else — which is the point of having the mode."""
    shuffled = steps_of(("get_pod_logs", "get_events", "get_metrics", "list_pods"))
    match = compare(steps_of(GOLDEN), shuffled, mode=SET)

    assert match.within_distance
    assert match.missing == ()


def test_set_still_reports_a_golden_action_nobody_took() -> None:
    """Ignoring order is not ignoring the actions."""
    match = compare(steps_of(GOLDEN), steps_of(("list_pods", "get_events")), mode=SET)

    assert not match.within_distance
    assert match.missing == ("get_pod_logs",)


def test_the_plan_example_counts_one_extra_and_no_redundancy() -> None:
    """Extra and redundant are different counts of different problems (FR-010)."""
    match = compare(steps_of(GOLDEN), steps_of(ACTUAL), mode=LCS, max_edit_distance=1)

    assert match.extra_actions == ("get_metrics",)
    assert match.redundant_calls == ()


def test_a_repeated_call_is_redundant_and_not_extra() -> None:
    """Asking the same question twice is a different defect from asking a new one.

    An agent that called ``get_events`` three times is looping; one that called
    ``get_metrics`` once wandered. Collapsing both into "extra" would report the
    same number for the two and leave nobody able to tell which happened.
    """
    repeated = steps_of(("list_pods", "get_events", "get_events", "get_events", "get_pod_logs"))
    match = compare(steps_of(GOLDEN), repeated, mode=LCS, max_edit_distance=2)

    assert match.redundant_calls == ("get_events", "get_events")
    assert match.extra_actions == ()


# -- parallel batches (FR-009) -------------------------------------------------


def test_a_parallel_batch_matches_in_any_internal_order() -> None:
    """The runtime schedules a batch how it likes; position is what is compared."""
    golden = (Step.of("list_pods"), Step.of("get_events", "get_pod_logs"))
    one_way = (Step.of("list_pods"), Step.of("get_events", "get_pod_logs"))
    other_way = (Step.of("list_pods"), Step.of("get_pod_logs", "get_events"))

    assert compare(golden, one_way, mode=STRICT).within_distance
    assert compare(golden, other_way, mode=STRICT).within_distance


def test_a_batch_that_did_more_than_the_golden_step_asked_for_is_extra_not_missing() -> None:
    """A golden single action is satisfied by a batch that contains it."""
    golden = steps_of(("list_pods", "get_events"))
    actual = (Step.of("list_pods"), Step.of("get_events", "get_metrics"))

    match = compare(golden, actual, mode=STRICT)

    assert match.within_distance
    assert match.missing == ()
    assert match.extra_actions == ("get_metrics",)


def test_iterations_group_concurrent_calls_into_one_step() -> None:
    """What the loop ran in one iteration is one position, however many calls it was."""
    steps = steps_from_iterations(
        ((1, "list_pods"), (2, "get_events"), (2, "get_pod_logs"), (3, "describe_pod"))
    )

    assert steps == (
        Step.of("list_pods"),
        Step.of("get_events", "get_pod_logs"),
        Step.of("describe_pod"),
    )


# -- the different-valid-route case (FR-011, SC-009) ---------------------------


def test_a_shorter_route_to_the_same_place_is_a_deviation() -> None:
    """Skipping a golden step is a trajectory finding, and it is reported as one.

    The accuracy axis is elsewhere and is unaffected; this only has to say that
    the route differed and by how much.
    """
    match = compare(steps_of(GOLDEN), steps_of(("get_events", "get_pod_logs")), mode=LCS)

    assert match.deviated
    assert match.missing == ("list_pods",)
    assert match.distance == 1


def test_the_exact_golden_route_is_not_a_deviation() -> None:
    """Nothing to report when the agent did what the key said."""
    match = compare(steps_of(GOLDEN), steps_of(GOLDEN), mode=STRICT)

    assert not match.deviated
    assert match.distance == 0


# -- mode names ----------------------------------------------------------------


def test_the_fixture_spelling_of_strict_resolves_to_strict() -> None:
    """Answer keys shipped with the corpus say ``exact``; the requirement says ``strict``."""
    assert normalise_mode("exact") == STRICT
    assert normalise_mode("strict") == STRICT
    assert normalise_mode("") == LCS


def test_an_unknown_mode_raises_rather_than_defaulting() -> None:
    """A typo that silently scored under another mode would be unattributable."""
    with pytest.raises(UnknownMatchingMode) as raised:
        normalise_mode("fuzzy")

    assert "fuzzy" in str(raised.value)


# -- a golden test over a fixed set (T014) -------------------------------------

#: Pinned behaviour: golden path, actual path, mode, allowance, and the verdict.
PINNED: tuple[tuple[tuple[str, ...], tuple[str, ...], str, int, bool, int], ...] = (
    (GOLDEN, GOLDEN, STRICT, 0, True, 0),
    (GOLDEN, ACTUAL, STRICT, 0, False, 1),
    (GOLDEN, ACTUAL, LCS, 1, True, 1),
    (GOLDEN, ACTUAL, LCS, 0, False, 1),
    (GOLDEN, ACTUAL, SET, 0, True, 1),
    (GOLDEN, ("get_events", "get_pod_logs"), LCS, 1, True, 1),
    (GOLDEN, ("get_events", "get_pod_logs"), SET, 0, False, 1),
    (GOLDEN, (), LCS, 3, True, 3),
    (GOLDEN, ("get_metrics",), LCS, 4, True, 4),
)


@pytest.mark.parametrize(("golden", "actual", "mode", "allowance", "passes", "distance"), PINNED)
def test_matching_behaviour_is_pinned_for_a_fixed_trajectory_set(
    golden: tuple[str, ...],
    actual: tuple[str, ...],
    mode: str,
    allowance: int,
    passes: bool,
    distance: int,
) -> None:
    """A change to any of these is a change to what the trajectory axis measures."""
    match = compare(steps_of(golden), steps_of(actual), mode=mode, max_edit_distance=allowance)

    assert match.within_distance is passes
    assert match.distance == distance
