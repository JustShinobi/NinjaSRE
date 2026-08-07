"""Scoring a real run, and comparing two releases' worth of them.

The synthetic corpus compares cleanly because every scenario runs every time. A
real-run suite does not: an experiment that misfired this release scored nothing,
and subtracting across that would report a flaky cluster as a regression — which
is the same mistake in a different place as scoring an invalid run.

So comparison narrows to what both releases actually scored, and says which runs
it had to drop. Those two together are what makes "comparable across releases"
a claim rather than a hope.
"""

from __future__ import annotations

from pathlib import Path

from config.constants.evaluation import AXIS_ACCURACY, SCORING_AXES
from tests.harness.realruns import (
    RealRunExpectation,
    RunValidity,
    axis_rates,
    comparable_pairs,
    not_comparable,
    report_of,
    score_real_run,
)
from tests.harness.regression.baseline import Baseline, BaselineStore
from tests.harness.regression.compare import compare
from tests.harness.scoring.composite import Observation

CART = RealRunExpectation(
    key="chaos/dns-error",
    suite="chaos",
    scenario_id="dns-error",
    failure_mode="dns_failure",
    severity="critical",
    difficulty=2,
    root_cause_category="network_failure",
    required_keywords=("dns", "resolution"),
    integrations=("kubernetes",),
    available_evidence=("kubernetes",),
)
POD = RealRunExpectation(
    key="chaos/pod-kill",
    suite="chaos",
    scenario_id="pod-kill",
    failure_mode="node_failure",
    severity="critical",
    difficulty=2,
    root_cause_category="infrastructure_failure",
    required_keywords=("pod", "terminated"),
    integrations=("kubernetes",),
    available_evidence=("kubernetes",),
)


def _right(expectation: RealRunExpectation) -> Observation:
    return Observation(
        root_cause_category=expectation.root_cause_category,
        answer_text=" ".join(expectation.required_keywords),
        evidence_sources=expectation.integrations,
        iterations=2,
        tokens=5_000,
        duration_seconds=3.0,
    )


def _wrong(expectation: RealRunExpectation) -> Observation:
    return Observation(
        root_cause_category="unknown",
        answer_text="nothing was established",
        iterations=2,
        tokens=5_000,
        duration_seconds=3.0,
    )


# --- the validity gate -------------------------------------------------------


def test_an_invalid_run_is_not_scored_at_all() -> None:
    score = score_real_run(
        CART, _wrong(CART), validity=RunValidity.INVALID, validity_detail="never bit"
    )

    assert score.score is None
    assert score.experiment_failure
    assert not score.agent_failure
    assert not score.passed


def test_a_valid_run_is_scored_on_every_axis_the_synthetic_suite_uses() -> None:
    score = score_real_run(CART, _right(CART), validity=RunValidity.VALID)

    assert score.score is not None
    assert tuple(axis.name for axis in score.score.axes) == SCORING_AXES
    assert score.passed


def test_the_pass_rate_is_over_the_scored_runs_not_the_attempted_ones() -> None:
    """Folding an invalid run into the denominator understates the agent."""
    report = report_of(
        [
            score_real_run(CART, _right(CART), validity=RunValidity.VALID),
            score_real_run(POD, _wrong(POD), validity=RunValidity.INVALID),
        ]
    )

    assert len(report.scored) == 1
    assert report.pass_rate == 1.0
    assert len(report.experiment_failures) == 1


def test_the_axes_are_reported_separately_for_real_runs_too() -> None:
    report = report_of([score_real_run(CART, _wrong(CART), validity=RunValidity.VALID)])

    rates = axis_rates(report)

    assert set(rates) == set(SCORING_AXES)
    assert rates[AXIS_ACCURACY] == 0.0


# --- comparable across releases ----------------------------------------------


def test_the_corpus_version_is_over_what_was_attempted_not_what_was_valid() -> None:
    """An experiment that misfired must not read as a corpus change."""
    everything = report_of(
        [
            score_real_run(CART, _right(CART), validity=RunValidity.VALID),
            score_real_run(POD, _right(POD), validity=RunValidity.VALID),
        ],
        attempted=[CART.key, POD.key],
    ).suite_score()
    one_misfired = report_of(
        [
            score_real_run(CART, _right(CART), validity=RunValidity.VALID),
            score_real_run(POD, _wrong(POD), validity=RunValidity.INVALID),
        ],
        attempted=[CART.key, POD.key],
    ).suite_score()

    assert everything.corpus_version == one_misfired.corpus_version


def test_two_releases_are_compared_over_the_runs_both_of_them_scored() -> None:
    before = report_of(
        [
            score_real_run(CART, _right(CART), validity=RunValidity.VALID),
            score_real_run(POD, _right(POD), validity=RunValidity.VALID),
        ],
        label="release-1",
        attempted=[CART.key, POD.key],
    ).suite_score()
    after = report_of(
        [
            score_real_run(CART, _wrong(CART), validity=RunValidity.VALID),
            score_real_run(POD, _right(POD), validity=RunValidity.INVALID),
        ],
        label="release-2",
        attempted=[CART.key, POD.key],
    ).suite_score()

    assert not_comparable(before, after) == ("chaos/pod-kill",)

    narrowed_before, narrowed_after = comparable_pairs(before, after)
    comparison = compare(narrowed_before, narrowed_after)

    assert comparison.corpus_matched
    accuracy = [delta for delta in comparison.axis_deltas if delta.axis == AXIS_ACCURACY]
    assert accuracy and accuracy[0].regressed


def test_a_real_run_baseline_is_stored_and_read_back_unchanged(tmp_path: Path) -> None:
    """A stored point is what turns "it got worse" into a subtraction."""
    suite = report_of(
        [score_real_run(CART, _right(CART), validity=RunValidity.VALID)],
        label="release-1",
        attempted=[CART.key],
    ).suite_score()
    store = BaselineStore(root=tmp_path)

    store.save(Baseline(identifier="chaos-release", suite=suite, note="pre-release run"))
    read = store.load("chaos-release")

    assert read.corpus_version == suite.corpus_version
    assert read.suite.pass_rate == suite.pass_rate
