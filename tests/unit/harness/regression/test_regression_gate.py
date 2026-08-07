"""Storing a known point, comparing against it, and failing a build for the right reason.

Four success criteria live in this file, and each one is a way a regression gate
goes wrong in practice.

**SC-002.** A real regression fails, and the failure names the scenario and the
axis. A gate that says "the suite got worse" sends somebody to read forty
scenarios; a gate that says "kubernetes/003 regressed on accuracy" sends them to
one.

**SC-005.** An unchanged codebase run N times does *not* fail. This is the one
that decides whether the gate survives its first month: gate on any movement of a
stochastic system and the build goes red on noise, somebody widens the tolerance
to shut it up, and the gate stops gating.

**SC-006.** A cost rise with unchanged correctness fails the cost gate and only
the cost gate. Separate buckets, so the trade-off is visible as a trade-off.

And the one the plan's risk table names: a corpus that changed is not an agent
that regressed, and the two must not be able to look alike.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from config.constants.evaluation import (
    AXIS_ACCURACY,
    AXIS_COST,
    AXIS_TRAJECTORY,
)
from tests.harness.loader import AnswerKey, GoldenTrajectory, Scenario
from tests.harness.regression.baseline import (
    Baseline,
    BaselineStore,
    UnknownBaseline,
)
from tests.harness.regression.compare import CorpusMismatch, compare
from tests.harness.regression.gate import GatePolicy, evaluate
from tests.harness.scoring.composite import Observation, score_observation
from tests.harness.scoring.matching import steps_of
from tests.harness.scoring.report import SuiteScore, corpus_version, summarise

pytestmark = pytest.mark.unit

GOLDEN = ("kubernetes_workload_events", "kubernetes_describe_workload")

ANSWER = AnswerKey(
    root_cause_category="resource_exhaustion",
    required_keywords=("memory", "limit"),
    model_response="ROOT_CAUSE: memory limit.\n",
    ruling_out_keywords=("deploy",),
    required_evidence_sources=("kubernetes",),
    golden_trajectory=GoldenTrajectory(
        ordered_actions=GOLDEN, matching="lcs", max_edit_distance=1, max_extra_actions=1
    ),
    max_investigation_loops=6,
)

RIGHT = "The container exceeded its memory limit; the 02:50 deploy is not implicated."
WRONG = "The pods look healthy; the 02:50 deploy is not implicated."


def scenario(scenario_id: str, *, difficulty: int = 2) -> Scenario:
    """Return one scenario value, with no fixtures behind it."""
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
        answer=ANSWER,
        evidence=(),
    )


CORPUS = (scenario("001-oom"), scenario("002-probe", difficulty=3))


def observation(
    *, correct: bool = True, tokens: int = 5_000, wandered: bool = False
) -> Observation:
    """Return one attempt's observations, in the dimensions these tests move."""
    trajectory = GOLDEN if not wandered else (*GOLDEN, "prometheus_query", "loki_query")
    return Observation(
        root_cause_category="resource_exhaustion" if correct else "healthy",
        answer_text=RIGHT if correct else WRONG,
        evidence_sources=("kubernetes",),
        trajectory=steps_of(trajectory),
        iterations=len(trajectory),
        tokens=tokens,
        duration_seconds=2.0,
    )


def run(
    *,
    label: str,
    attempts: int = 5,
    correct_rate: float = 1.0,
    tokens: int = 5_000,
    wandered: bool = False,
    seed: int = 7,
    corpus=CORPUS,
) -> SuiteScore:
    """Return a scored suite run over ``corpus``, with the outcome shaped as asked."""
    chance = random.Random(seed)
    scores = []
    for subject in corpus:
        for attempt in range(1, attempts + 1):
            correct = chance.random() < correct_rate
            scores.append(
                score_observation(
                    subject,
                    observation(correct=correct, tokens=tokens, wandered=wandered),
                    attempt=attempt,
                )
            )
    return summarise(
        scores, label=label, corpus_version=corpus_version(found.key for found in corpus)
    )


# -- storing a baseline (T029, FR-021) -----------------------------------------


def test_a_baseline_is_stored_and_read_back_by_identifier(tmp_path: Path) -> None:
    """ "Compared to what?" always has an answer, and the answer is a file."""
    store = BaselineStore(root=tmp_path)
    stored = Baseline(identifier="v0.28.0", suite=run(label="release"))

    store.save(stored)

    assert store.identifiers() == ("v0.28.0",)
    assert store.load("v0.28.0").suite == stored.suite


def test_a_baseline_records_the_corpus_it_was_measured_over(tmp_path: Path) -> None:
    """The plan's risk: a fixture change must not be able to look like a regression."""
    store = BaselineStore(root=tmp_path)
    store.save(Baseline(identifier="v0.28.0", suite=run(label="release")))

    assert store.load("v0.28.0").corpus_version == corpus_version(found.key for found in CORPUS)


def test_asking_for_a_baseline_that_was_never_stored_lists_what_is(tmp_path: Path) -> None:
    """The person seeing this is choosing an identifier, so show them the choices."""
    store = BaselineStore(root=tmp_path)
    store.save(Baseline(identifier="v0.27.0", suite=run(label="previous")))

    with pytest.raises(UnknownBaseline) as raised:
        store.load("v0.99.0")

    assert "v0.99.0" in str(raised.value)
    assert "v0.27.0" in str(raised.value)


def test_a_baseline_round_trips_through_its_record(tmp_path: Path) -> None:
    """A baseline that could be written and not read back is a screenshot."""
    stored = Baseline(identifier="v0.28.0", suite=run(label="release"), note="first release")

    assert Baseline.from_record(stored.to_record()) == stored


# -- comparison (T030, FR-017) -------------------------------------------------


def test_a_comparison_is_per_scenario_and_per_axis() -> None:
    """One number for the suite would not say where to look."""
    before = run(label="before")
    after = run(label="after", correct_rate=0.0)

    comparison = compare(before, after)

    keys = {delta.scenario for delta in comparison.axis_deltas}
    assert keys == {"kubernetes/001-oom", "kubernetes/002-probe"}

    accuracy = [
        delta
        for delta in comparison.for_scenario("kubernetes/001-oom")
        if delta.axis == AXIS_ACCURACY
    ]
    assert accuracy[0].delta < 0.0


def test_comparing_two_different_corpora_refuses_rather_than_subtracting() -> None:
    """A corpus change requires a new baseline, and the refusal says so."""
    before = run(label="before")
    after = run(label="after", corpus=(scenario("003-new"),))

    with pytest.raises(CorpusMismatch) as raised:
        compare(before, after)

    assert "corpus" in str(raised.value).lower()


def test_a_corpus_change_can_be_compared_deliberately_and_says_what_moved() -> None:
    """Refusing by default is not refusing at all; the reader has to be able to look."""
    before = run(label="before")
    after = run(label="after", corpus=(CORPUS[0], scenario("003-new")))

    comparison = compare(before, after, strict_corpus=False)

    assert comparison.missing_scenarios == ("kubernetes/002-probe",)
    assert comparison.new_scenarios == ("kubernetes/003-new",)
    assert not comparison.corpus_matched


# -- the gate (T031–T035, SC-002, SC-005, SC-006) ------------------------------


def test_an_unchanged_codebase_run_repeatedly_does_not_fail_the_gate() -> None:
    """SC-005. The criterion the gate's survival depends on.

    Ten pairs of runs of the same stochastic system, at the same true pass rate,
    with different seeds. None of them may fail the build.

    Ten attempts each, which is what a variance-aware comparison actually needs.
    At five, a run of an unchanged 80%-accurate system produces "five out of five
    then two out of five" often enough to be seen in a fixture this size, and no
    honest rule can call that a regression — so the answer is to measure it
    properly rather than to widen the gate until it forgives everything.
    """
    policy = GatePolicy()
    for seed in range(10):
        before = run(label="before", attempts=10, correct_rate=0.8, seed=seed)
        after = run(label="after", attempts=10, correct_rate=0.8, seed=seed + 100)

        result = evaluate(compare(before, after), policy)

        assert result.passed, f"seed {seed}: noise failed the gate — {result.render()}"


def test_a_deliberate_accuracy_regression_fails_and_names_the_scenario_and_axis() -> None:
    """SC-002. Everything right, then nothing right, and the report says where."""
    before = run(label="before", attempts=5)
    after = run(label="after", attempts=5, correct_rate=0.0)

    result = evaluate(compare(before, after))

    assert not result.passed
    assert result.correctness
    named = {failure.scenario for failure in result.correctness}
    assert "kubernetes/001-oom" in named
    assert all(failure.axis == AXIS_ACCURACY for failure in result.correctness)

    text = result.render()
    assert "kubernetes/001-oom" in text
    assert AXIS_ACCURACY in text


def test_a_cost_regression_with_unchanged_accuracy_fails_only_the_cost_gate() -> None:
    """SC-006, exactly: correctness untouched, the bill tripled."""
    before = run(label="before", attempts=3, tokens=5_000)
    after = run(label="after", attempts=3, tokens=15_000)

    result = evaluate(compare(before, after))

    assert not result.passed
    assert result.cost
    assert not result.correctness
    assert not result.trajectory
    assert any("tokens" in failure.detail for failure in result.cost)


def test_a_trajectory_regression_is_its_own_bucket() -> None:
    """A longer route with the same answer is a finding of its own."""
    before = run(label="before", attempts=3)
    after = run(label="after", attempts=3, wandered=True)

    result = evaluate(compare(before, after))

    assert result.trajectory
    assert not result.correctness
    assert any(failure.axis == AXIS_TRAJECTORY for failure in result.trajectory)


def test_a_drop_inside_the_baselines_own_spread_is_not_a_regression() -> None:
    """FR-019: gating accounts for variance, so noise does not fail builds."""
    before = run(label="before", attempts=5, correct_rate=0.6, seed=1)
    after = run(label="after", attempts=5, correct_rate=0.6, seed=2)

    forgiving = evaluate(compare(before, after), GatePolicy())
    unforgiving = evaluate(
        compare(before, after),
        GatePolicy(correctness_tolerance=0.0, sigma_allowance=0.0),
    )

    assert forgiving.passed
    assert not unforgiving.passed, "the fixture has to actually move, or this proves nothing"


def test_a_single_attempt_comparison_falls_back_to_the_bare_tolerance() -> None:
    """One attempt has no spread, and pretending otherwise would gate on nothing."""
    before = run(label="before", attempts=1)
    after = run(label="after", attempts=1, correct_rate=0.0)

    result = evaluate(compare(before, after))

    assert not result.passed
    assert result.correctness


def test_a_large_percentage_rise_on_a_tiny_base_is_not_a_cost_regression() -> None:
    """The offline corpus finds this within one release: 30ms then 42ms is +40% and nothing.

    Percentage alone would put the gate permanently red over scheduling jitter,
    which is the failure mode that gets a gate disabled rather than fixed.
    """
    before = run(label="before", attempts=3, tokens=5_000)
    after = run(label="after", attempts=3, tokens=5_100)

    result = evaluate(compare(before, after))

    assert result.passed
    assert not result.cost


def test_a_token_rise_past_both_the_share_and_the_absolute_floor_still_fails() -> None:
    """The floor must not become a way for a real regression to slip through."""
    before = run(label="before", attempts=3, tokens=5_000)
    after = run(label="after", attempts=3, tokens=9_000)

    assert not evaluate(compare(before, after)).passed


def test_an_improvement_is_never_a_gate_failure() -> None:
    """Obvious, and worth pinning: a gate that fired on good news would be disabled."""
    before = run(label="before", attempts=5, correct_rate=0.0)
    after = run(label="after", attempts=5, correct_rate=1.0)

    result = evaluate(compare(before, after))

    assert result.passed
    assert result.improvements


def test_the_gate_reports_every_regression_rather_than_the_first() -> None:
    """A gate that stopped at the first failure would need N builds to find N problems."""
    before = run(label="before", attempts=3, tokens=5_000)
    after = run(label="after", attempts=3, correct_rate=0.0, tokens=20_000, wandered=True)

    result = evaluate(compare(before, after))

    assert result.correctness and result.cost and result.trajectory
    assert {failure.gate for failure in result.failures} == {
        "correctness",
        "trajectory",
        "cost",
    }


def test_a_gate_result_names_the_baseline_it_was_measured_against() -> None:
    """A published pass has to carry what it was compared to."""
    before = run(label="v0.27.0", attempts=3)
    after = run(label="working tree", attempts=3)

    result = evaluate(compare(before, after))

    assert "v0.27.0" in result.render()
    assert result.to_record()["baseline"] == "v0.27.0"


def test_the_axes_the_gate_watches_are_split_the_way_the_requirement_says() -> None:
    """FR-020: correctness and cost are separate gates, not one with a footnote."""
    policy = GatePolicy()

    assert AXIS_ACCURACY in policy.correctness_axes
    assert AXIS_COST not in policy.correctness_axes
    assert policy.cost_tolerance > policy.correctness_tolerance
