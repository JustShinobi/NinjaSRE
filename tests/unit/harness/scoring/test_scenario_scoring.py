"""Assembling five axes into one score, and many scores into one number with a spread.

Two properties are asserted here and both are things a simpler design loses.

**Five results, always.** Even for a scenario whose answer key asserts two axes,
even for one that failed on the first axis checked. A composite that returned
early would make "why did this fail" answerable only by re-running, which is the
cost the whole feature is here to remove.

**A mean with a spread beside it.** Four passes in five is not eighty percent
the way a single run is; it is a scenario the agent solves *usually*, and a
release that turns it into five in five has done something. Reporting the mean
alone makes those two the same shape of number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.evaluation import (
    AXIS_ACCURACY,
    AXIS_ADVERSARIAL,
    AXIS_COST,
    AXIS_EVIDENCE,
    AXIS_TRAJECTORY,
    SCORING_AXES,
)
from core.domain.diagnosis.result import Claim
from tests.harness.loader import AnswerKey, GoldenTrajectory, Scenario
from tests.harness.scoring.composite import Observation, ScenarioScore, score_observation
from tests.harness.scoring.matching import Step, steps_of
from tests.harness.scoring.report import SuiteScore, summarise

pytestmark = pytest.mark.unit


def answer(**overrides: object) -> AnswerKey:
    """Return an answer key asserting every axis, with fields overridden."""
    fields: dict[str, object] = {
        "root_cause_category": "resource_exhaustion",
        "required_keywords": ("memory", "limit"),
        "model_response": "ROOT_CAUSE: memory limit.\n",
        "forbidden_categories": ("healthy",),
        "ruling_out_keywords": ("deploy",),
        "required_evidence_sources": ("kubernetes",),
        "golden_trajectory": GoldenTrajectory(
            ordered_actions=("list_pods", "get_events"),
            matching="lcs",
            max_edit_distance=1,
            max_extra_actions=1,
        ),
        "max_investigation_loops": 5,
    }
    fields.update(overrides)
    return AnswerKey(**fields)  # type: ignore[arg-type]


def scenario(key: AnswerKey, *, difficulty: int = 2, scenario_id: str = "001-oom") -> Scenario:
    """Return a scenario value carrying ``key``, with no fixtures behind it."""
    return Scenario(
        directory=Path("kubernetes") / scenario_id,
        suite="kubernetes",
        scenario_id=scenario_id,
        failure_mode="memory_exhaustion",
        severity="critical",
        difficulty=difficulty,
        adversarial_signals=("coincident_deployment",),
        available_evidence=("kubernetes",),
        integrations=("kubernetes",),
        alert={"text": "checkout is restarting"},
        answer=key,
        evidence=(),
    )


PERFECT = Observation(
    root_cause_category="resource_exhaustion",
    answer_text="The container exceeded its memory limit; the 02:50 deploy is not implicated.",
    evidence_sources=("kubernetes",),
    validated_claims=(Claim(statement="the limit was 512Mi", evidence_ids=("e1",)),),
    held_evidence_ids=frozenset({"e1"}),
    trajectory=steps_of(("list_pods", "get_events")),
    iterations=2,
    tokens=4_000,
    duration_seconds=3.0,
)


# -- composite (T015, T016, SC-001) --------------------------------------------


def test_a_score_carries_all_five_axes_in_the_reading_order() -> None:
    """SC-001, as a shape assertion rather than a count."""
    score = score_observation(scenario(answer()), PERFECT)

    assert tuple(axis.name for axis in score.axes) == SCORING_AXES


def test_a_scenario_passes_only_when_every_asserted_axis_passes() -> None:
    """FR-007. One break on one axis is enough, and the rest still report."""
    wandering = Observation(
        **{
            **PERFECT.as_overrides(),
            "trajectory": steps_of(
                ("list_pods", "get_events", "get_metrics", "describe_pod", "get_pod_logs")
            ),
        }
    )
    score = score_observation(scenario(answer()), wandering)

    assert not score.passed
    assert score.failed_axes == (AXIS_TRAJECTORY,)
    assert score.axis(AXIS_ACCURACY) is not None
    assert score.axis(AXIS_ACCURACY).passed  # type: ignore[union-attr]
    assert score.axis(AXIS_EVIDENCE).passed  # type: ignore[union-attr]


def test_an_unasserted_axis_is_reported_as_unasserted_and_does_not_gate() -> None:
    """Partial results are reported, never collapsed (T016)."""
    bare = AnswerKey(
        root_cause_category="resource_exhaustion",
        required_keywords=("memory",),
        model_response="ROOT_CAUSE: memory.\n",
    )
    score = score_observation(scenario(bare), PERFECT)

    assert score.passed
    adversarial = score.axis(AXIS_ADVERSARIAL)
    assert adversarial is not None
    assert not adversarial.applicable
    assert score.asserted_axes == (AXIS_ACCURACY, AXIS_EVIDENCE, AXIS_COST)


def test_a_score_round_trips_through_its_record() -> None:
    """A stored corpus run has to be re-readable, or a baseline is a screenshot."""
    score = score_observation(scenario(answer()), PERFECT)

    assert ScenarioScore.from_record(score.to_record()) == score


# -- the different-route case, at composite level (T013, SC-009) ---------------


def test_a_different_route_to_the_right_answer_fails_no_correctness_axis() -> None:
    """SC-009: the deviation is on the trajectory axis and nowhere else."""
    other_route = Observation(
        **{
            **PERFECT.as_overrides(),
            "trajectory": steps_of(("get_events",)),
            "iterations": 1,
        }
    )
    score = score_observation(scenario(answer()), other_route)

    assert score.axis(AXIS_ACCURACY).passed  # type: ignore[union-attr]
    assert score.axis(AXIS_EVIDENCE).passed  # type: ignore[union-attr]
    assert score.axis(AXIS_ADVERSARIAL).passed  # type: ignore[union-attr]
    assert score.deviated_from_golden
    assert score.different_valid_route, (
        "the right answer by another route is a deviation, not an accuracy failure"
    )


def test_a_wrong_answer_by_a_different_route_is_not_reported_as_a_deviation() -> None:
    """The deviation report is for runs that were *right*; the rest are just wrong."""
    wrong = Observation(
        **{
            **PERFECT.as_overrides(),
            "root_cause_category": "healthy",
            "trajectory": steps_of(("get_events",)),
        }
    )
    score = score_observation(scenario(answer()), wrong)

    assert not score.different_valid_route
    assert AXIS_ACCURACY in score.failed_axes


# -- parallel batches reach the axis (FR-009) ----------------------------------


def test_calls_made_in_one_iteration_are_one_position() -> None:
    """A batch that covers two golden steps is not two deviations."""
    batched = Observation(
        **{**PERFECT.as_overrides(), "trajectory": (Step.of("list_pods", "get_events"),)}
    )
    score = score_observation(scenario(answer()), batched)

    trajectory = score.axis(AXIS_TRAJECTORY)
    assert trajectory is not None
    assert trajectory.measurements["distance"] <= 1


# -- suite reporting (T017–T020, FR-019) ---------------------------------------


def suite_of(*outcomes: bool, difficulty: int = 2, key: str = "kubernetes/001-oom") -> SuiteScore:
    """Return a suite score over N attempts at one scenario, passing as given."""
    subject = scenario(answer(), difficulty=difficulty, scenario_id=key.split("/")[1])
    scores = []
    for attempt, passed in enumerate(outcomes, start=1):
        observation = (
            PERFECT
            if passed
            else Observation(**{**PERFECT.as_overrides(), "root_cause_category": "healthy"})
        )
        scores.append(score_observation(subject, observation, attempt=attempt))
    return summarise(scores, label="under test")


def test_a_suite_reports_the_mean_and_the_spread_together() -> None:
    """FR-019. Four in five is not the same signal as five in five."""
    report = suite_of(True, True, True, True, False)
    found = report.scenarios[0]

    assert found.attempts == 5
    assert found.pass_rate == pytest.approx(0.8)
    assert found.pass_stdev > 0.0


def test_an_unvarying_scenario_reports_no_spread() -> None:
    """Five identical outcomes have a standard deviation of zero, and say so."""
    report = suite_of(True, True, True)

    assert report.scenarios[0].pass_stdev == pytest.approx(0.0)
    assert report.pass_rate == pytest.approx(1.0)


def test_axis_rates_are_reported_per_axis_not_only_overall() -> None:
    """A suite that only reported a solve rate could not price a mechanism per axis."""
    report = suite_of(True, False, True, True)

    assert report.axis_rate(AXIS_ACCURACY) == pytest.approx(0.75)
    assert report.axis_rate(AXIS_TRAJECTORY) == pytest.approx(1.0)


def test_reporting_stratifies_by_difficulty_and_by_failure_mode() -> None:
    """T019. An improvement on the easy rung is not the same finding as one everywhere."""
    easy = score_observation(scenario(answer(), difficulty=1, scenario_id="001-a"), PERFECT)
    hard = score_observation(
        scenario(answer(), difficulty=4, scenario_id="002-b"),
        Observation(**{**PERFECT.as_overrides(), "root_cause_category": "healthy"}),
    )
    report = summarise((easy, hard))

    levels = {found.difficulty: found for found in report.by_difficulty()}
    assert levels[1].pass_rate == pytest.approx(1.0)
    assert levels[4].pass_rate == pytest.approx(0.0)

    modes = {found.name: found for found in report.by_failure_mode()}
    assert modes["memory_exhaustion"].attempts == 2


def test_the_report_is_both_readable_and_machine_readable() -> None:
    """T020. One report, two renderings, and the second round-trips."""
    report = suite_of(True, False)

    text = report.render()
    assert "kubernetes/001-oom" in text
    assert "accuracy" in text

    assert SuiteScore.from_record(report.to_record()) == report


def test_failure_modes_are_reported_by_which_axis_failed() -> None:
    """ "Two failures" is not a finding; "two accuracy failures" is."""
    report = suite_of(True, False, False)

    assert report.failures_by_axis()[AXIS_ACCURACY] == 2
    assert report.failures_by_axis().get(AXIS_COST, 0) == 0
