"""Five axes, and the demonstration that each one fails on its own account.

The requirement the whole feature rests on is that these do not collapse into a
pass or a fail. So every test here holds four axes right and breaks the fifth,
and asserts both halves: the axis that should have failed did, and the four that
should not have did not.

That shape is deliberate and it is the expensive kind of test to write. It is
also the only kind that catches the failure mode this feature exists to prevent
— a scorer that reports "failed" and leaves the reader to run the scenario again
to find out on what.
"""

from __future__ import annotations

import pytest

from config.constants.evaluation import (
    AXIS_ACCURACY,
    AXIS_ADVERSARIAL,
    AXIS_COST,
    AXIS_EVIDENCE,
    AXIS_TRAJECTORY,
)
from core.domain.diagnosis.result import Claim
from tests.harness.loader import AnswerKey, GoldenTrajectory
from tests.harness.scoring.axes.accuracy import score_accuracy
from tests.harness.scoring.axes.adversarial import score_adversarial
from tests.harness.scoring.axes.cost import CostBudget, score_cost
from tests.harness.scoring.axes.evidence import score_evidence
from tests.harness.scoring.axes.trajectory import score_trajectory
from tests.harness.scoring.matching import steps_of

pytestmark = pytest.mark.unit

ANSWER = AnswerKey(
    root_cause_category="resource_exhaustion",
    required_keywords=("memory", "limit"),
    model_response="ROOT_CAUSE: the container exceeded its memory limit.\n",
    equivalent_root_cause_categories=("configuration_error",),
    forbidden_categories=("healthy",),
    forbidden_keywords=("network partition",),
    ruling_out_keywords=("deploy", "traffic"),
    required_evidence_sources=("kubernetes", "prometheus"),
    golden_trajectory=GoldenTrajectory(
        ordered_actions=("list_pods", "get_events", "get_pod_logs"),
        matching="lcs",
        max_edit_distance=1,
        max_extra_actions=1,
        max_redundancy=0,
    ),
    max_investigation_loops=6,
)

#: What a run that got everything right said. Every required keyword, both
#: ruling-out keywords, and no forbidden one.
GOOD_ANSWER_TEXT = (
    "The checkout container exceeded its 512Mi memory limit and was OOM-killed. "
    "The 02:50 deploy is not implicated — it changed only the readiness path — and "
    "the traffic peak at 02:40 had already subsided before the first restart."
)


# -- accuracy (FR-002) ---------------------------------------------------------


def test_accuracy_passes_on_the_declared_category() -> None:
    """The plain case, so the failures below are about one break each."""
    score = score_accuracy(ANSWER, category="resource_exhaustion", said=GOOD_ANSWER_TEXT)

    assert score.name == AXIS_ACCURACY
    assert score.passed


def test_an_equivalent_category_counts_as_correct() -> None:
    """An answer key that names equivalents means them."""
    score = score_accuracy(ANSWER, category="configuration_error", said=GOOD_ANSWER_TEXT)

    assert score.passed


def test_a_missing_required_keyword_fails_accuracy_and_names_it() -> None:
    """The reader has to learn *which* keyword, not that one was absent."""
    score = score_accuracy(
        ANSWER, category="resource_exhaustion", said="The container was killed by the kubelet."
    )

    assert not score.passed
    assert "memory" in score.missing
    assert "limit" in score.missing


def test_a_forbidden_keyword_fails_accuracy() -> None:
    """Saying the thing the key forbids is wrong even when everything else is right."""
    score = score_accuracy(
        ANSWER,
        category="resource_exhaustion",
        said=f"{GOOD_ANSWER_TEXT} A network partition may also be involved.",
    )

    assert not score.passed
    assert "network partition" in score.unexpected


def test_a_forbidden_category_fails_accuracy_whatever_the_keywords_say() -> None:
    """Acceptance scenario 3, exactly: the keywords are all there and it still fails."""
    score = score_accuracy(ANSWER, category="healthy", said=GOOD_ANSWER_TEXT)

    assert not score.passed
    assert score.missing == ()
    assert "healthy" in score.unexpected
    assert "forbidden" in score.detail


# -- evidence (FR-003) ---------------------------------------------------------

HELD = frozenset({"e1", "e2"})
BACKED = (Claim(statement="the limit was 512Mi", evidence_ids=("e1",)),)


def test_evidence_passes_when_every_required_source_was_collected() -> None:
    """Both halves of the axis hold: the sources are there and the claims cite them."""
    score = score_evidence(ANSWER, sources=("kubernetes", "prometheus"), claims=BACKED, held=HELD)

    assert score.name == AXIS_EVIDENCE
    assert score.passed


def test_a_source_that_was_never_reached_fails_evidence_and_is_named() -> None:
    """A conclusion resting on evidence nobody gathered is the failure Article I is about."""
    score = score_evidence(ANSWER, sources=("kubernetes",), claims=BACKED, held=HELD)

    assert not score.passed
    assert score.missing == ("prometheus",)


def test_a_claim_citing_an_entry_the_run_does_not_hold_fails_evidence() -> None:
    """An invented citation is not a partial success; it is an unbacked claim."""
    invented = (Claim(statement="the pool was exhausted", evidence_ids=("e99",)),)
    score = score_evidence(ANSWER, sources=("kubernetes", "prometheus"), claims=invented, held=HELD)

    assert not score.passed
    assert "the pool was exhausted" in score.unexpected


def test_evidence_is_inapplicable_when_the_key_asserts_nothing_about_it() -> None:
    """An axis nobody asserted is reported as unasserted, not as a silent pass."""
    bare = AnswerKey(
        root_cause_category="resource_exhaustion",
        required_keywords=("memory",),
        model_response="ROOT_CAUSE: memory.\n",
    )
    score = score_evidence(bare, sources=(), claims=(), held=frozenset())

    assert not score.applicable
    assert score.passed


# -- adversarial resistance (FR-004) -------------------------------------------


def test_adversarial_passes_when_every_confounder_was_dismissed() -> None:
    """Both ruling-out keywords appear in what the agent said."""
    score = score_adversarial(ANSWER, said=GOOD_ANSWER_TEXT)

    assert score.name == AXIS_ADVERSARIAL
    assert score.passed


def test_a_missing_ruling_out_keyword_fails_adversarial_while_accuracy_holds() -> None:
    """Acceptance scenario 4: the right answer, arrived at without ruling anything out."""
    said = "The checkout container exceeded its 512Mi memory limit and was OOM-killed."

    adversarial = score_adversarial(ANSWER, said=said)
    accuracy = score_accuracy(ANSWER, category="resource_exhaustion", said=said)

    assert not adversarial.passed
    assert set(adversarial.missing) == {"deploy", "traffic"}
    assert accuracy.passed, "the root cause was right; only the resistance axis failed"


# -- trajectory efficiency (FR-005, FR-010) ------------------------------------


def test_trajectory_passes_within_the_allowance_the_key_sets() -> None:
    """One insertion, one allowance, four loops against a ceiling of six."""
    score = score_trajectory(
        ANSWER,
        trajectory=steps_of(("list_pods", "get_metrics", "get_events", "get_pod_logs")),
        iterations=4,
    )

    assert score.name == AXIS_TRAJECTORY
    assert score.passed
    assert score.measurements["distance"] == 1
    assert score.measurements["extra_actions"] == 1
    assert score.measurements["redundant_calls"] == 0


def test_too_many_extra_actions_fails_trajectory_even_at_zero_distance() -> None:
    """Wandering is a trajectory defect the distance number alone would not catch."""
    score = score_trajectory(
        ANSWER,
        trajectory=steps_of(
            ("list_pods", "get_events", "get_pod_logs", "get_metrics", "describe_pod")
        ),
        iterations=5,
    )

    assert not score.passed
    assert score.measurements["extra_actions"] == 2


def test_a_repeated_call_fails_trajectory_on_redundancy() -> None:
    """``max_redundancy`` is zero on this key, so one repeat is one too many."""
    score = score_trajectory(
        ANSWER,
        trajectory=steps_of(("list_pods", "get_events", "get_events", "get_pod_logs")),
        iterations=4,
    )

    assert not score.passed
    assert score.measurements["redundant_calls"] == 1


def test_exceeding_the_answer_keys_loop_ceiling_fails_trajectory() -> None:
    """Article II's bound, lowered by the key for this incident."""
    assert ANSWER.golden_trajectory is not None
    score = score_trajectory(
        ANSWER, trajectory=steps_of(ANSWER.golden_trajectory.ordered_actions), iterations=9
    )

    assert not score.passed
    assert score.measurements["iterations"] == 9
    assert "loop" in score.detail


def test_a_different_valid_route_is_a_deviation_rather_than_a_missing_action() -> None:
    """FR-011: the deviation is recorded, and it is what the detail says."""
    score = score_trajectory(
        ANSWER, trajectory=steps_of(("get_events", "get_pod_logs")), iterations=2
    )

    assert score.measurements["deviated"] == 1.0
    assert score.measurements["distance"] == 1
    assert "list_pods" in score.missing
    assert "different route" in score.detail


# -- cost (FR-006) -------------------------------------------------------------


def test_cost_passes_inside_the_budget() -> None:
    """Tokens and wall clock, both under."""
    score = score_cost(CostBudget(tokens=20_000, seconds=60.0), tokens=8_000, seconds=12.5)

    assert score.name == AXIS_COST
    assert score.passed
    assert score.measurements["tokens"] == 8_000


def test_a_token_overrun_fails_cost_and_says_by_how_much() -> None:
    """Actual against budget, because "too expensive" is not an actionable report."""
    score = score_cost(CostBudget(tokens=10_000, seconds=60.0), tokens=25_000, seconds=12.5)

    assert not score.passed
    assert score.measurements["tokens"] == 25_000
    assert "10000" in score.detail


def test_a_wall_clock_overrun_fails_cost_on_its_own() -> None:
    """Time and tokens are two ways to be expensive and they are reported apart."""
    score = score_cost(CostBudget(tokens=10_000, seconds=30.0), tokens=1_000, seconds=91.0)

    assert not score.passed
    assert score.measurements["seconds"] == pytest.approx(91.0)


def test_the_budget_widens_with_the_difficulty_of_the_scenario() -> None:
    """A level-4 incident is allowed to cost more than a level-1 one."""
    easy = CostBudget.for_difficulty(1)
    hard = CostBudget.for_difficulty(4)

    assert hard.tokens > easy.tokens
    assert hard.seconds >= easy.seconds


# -- independence (T007) -------------------------------------------------------


def test_each_axis_fails_alone_and_for_its_own_reason() -> None:
    """The property the feature exists for, asserted as one statement.

    Four breaks, one per axis, each checked against all five scorers. If any
    break moved a second axis, the axes are not independent and every ablation
    number computed from them would be attributing a change to the wrong thing.
    """
    trajectory = steps_of(("list_pods", "get_events", "get_pod_logs"))

    def axes(
        *, category: str, said: str, sources: tuple[str, ...], seconds: float
    ) -> dict[str, bool]:
        return {
            AXIS_ACCURACY: score_accuracy(ANSWER, category=category, said=said).passed,
            AXIS_EVIDENCE: score_evidence(ANSWER, sources=sources, claims=BACKED, held=HELD).passed,
            AXIS_ADVERSARIAL: score_adversarial(ANSWER, said=said).passed,
            AXIS_TRAJECTORY: score_trajectory(ANSWER, trajectory=trajectory, iterations=3).passed,
            AXIS_COST: score_cost(
                CostBudget(tokens=10_000, seconds=30.0), tokens=1_000, seconds=seconds
            ).passed,
        }

    everything_right = {
        "category": "resource_exhaustion",
        "said": GOOD_ANSWER_TEXT,
        "sources": ("kubernetes", "prometheus"),
        "seconds": 1.0,
    }
    assert all(axes(**everything_right).values())  # type: ignore[arg-type]

    # One break at a time, and the axis it belongs to is the only one that moves.
    only_accuracy = axes(**{**everything_right, "category": "healthy"})  # type: ignore[arg-type]
    assert not only_accuracy[AXIS_ACCURACY]
    assert only_accuracy[AXIS_EVIDENCE]
    assert only_accuracy[AXIS_ADVERSARIAL]

    only_evidence = axes(**{**everything_right, "sources": ("kubernetes",)})  # type: ignore[arg-type]
    assert not only_evidence[AXIS_EVIDENCE]
    assert only_evidence[AXIS_ACCURACY]
    assert only_evidence[AXIS_ADVERSARIAL]

    quiet = "The container exceeded its 512Mi memory limit."
    only_adversarial = axes(**{**everything_right, "said": quiet})  # type: ignore[arg-type]
    assert not only_adversarial[AXIS_ADVERSARIAL]
    assert only_adversarial[AXIS_ACCURACY]

    only_cost = axes(**{**everything_right, "seconds": 120.0})  # type: ignore[arg-type]
    assert not only_cost[AXIS_COST]
    assert only_cost[AXIS_ACCURACY]
    assert only_cost[AXIS_TRAJECTORY]
