"""The baseline plus one run per arm, and the table that comes out of it.

The arm runner here is a small deterministic policy rather than a script: it
decides what the agent found from which mechanisms were switched on, the same way
the strategy-value scenario does. That is what lets one test assert that memory
was worth thirteen points and another assert that a harmful mechanism is flagged,
without either of them being a fixture with the answer written in it.

The number that matters is the subtraction. A report that only listed each arm's
pass rate would leave the reader doing it, and the sign of the result — the one
case where the mechanism is hurting — is exactly what a reader skims past.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from config.constants.evaluation import (
    ABLATION_MECHANISMS,
    AXIS_ACCURACY,
    AXIS_TRAJECTORY,
    BASELINE_ARM,
)
from tests.harness.ablation.config import AblationConfig, baseline_config, one_at_a_time
from tests.harness.ablation.report import AblationReport, report_for
from tests.harness.ablation.runner import AblationResult, run_ablation
from tests.harness.ablation.switches import MechanismSwitches
from tests.harness.loader import AnswerKey, GoldenTrajectory, Scenario
from tests.harness.scoring.composite import Observation
from tests.harness.scoring.matching import steps_of

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


def scenario(scenario_id: str, *, difficulty: int) -> Scenario:
    """Return one scenario value at ``difficulty``, with no fixtures behind it."""
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


CORPUS = (scenario("001-easy", difficulty=1), scenario("002-hard", difficulty=3))


def observation(*, correct: bool, wandered: bool) -> Observation:
    """Return what one attempt did, in the two dimensions the arms move."""
    trajectory = GOLDEN if not wandered else (*GOLDEN, "kubernetes_pod_logs", "prometheus_query")
    return Observation(
        root_cause_category="resource_exhaustion" if correct else "healthy",
        answer_text=RIGHT if correct else WRONG,
        evidence_sources=("kubernetes",),
        trajectory=steps_of(trajectory),
        iterations=len(trajectory),
        tokens=5_000,
        duration_seconds=2.0,
    )


def policy_arm(*, helps: Sequence[str] = (), harms: Sequence[str] = ()):
    """Return an arm runner whose outcome depends on which mechanisms are on.

    ``helps`` names the mechanisms a level-3 scenario needs to be solved at all;
    ``harms`` names one whose presence makes the agent wander. Both are decided
    from the switches the runner hands in, so an arm that did not actually differ
    would produce an identical result and the contribution would be zero.
    """

    async def run(subject: Scenario, switches: MechanismSwitches, attempt: int) -> Observation:
        correct = subject.difficulty < 3 or all(switches.enabled(name) for name in helps)
        wandered = any(switches.enabled(name) for name in harms)
        return observation(correct=correct, wandered=wandered)

    return run


# -- the runner (T025) ---------------------------------------------------------


async def test_the_runner_produces_the_baseline_and_one_result_per_arm() -> None:
    """Nine runs for eight mechanisms, and the baseline is first."""
    result = await run_ablation(CORPUS, arm=policy_arm(helps=("memory_read",)))

    assert result.baseline.config.name == BASELINE_ARM
    assert len(result.arms) == len(ABLATION_MECHANISMS) + 1
    assert result.arm("no-topology") is not None


async def test_every_arm_runs_the_whole_corpus_the_same_number_of_times() -> None:
    """FR-013: identical in every respect except the mechanism."""
    result = await run_ablation(CORPUS, arm=policy_arm(), attempts=3)

    for arm in result.arms:
        assert arm.suite.attempts == len(CORPUS) * 3
        assert {found.key for found in arm.suite.scenarios} == {found.key for found in CORPUS}


async def test_each_arm_records_the_configuration_it_ran_under() -> None:
    """SC-004 again, at the level a report reads: the arm's trace is on the result."""
    result = await run_ablation(CORPUS, arm=policy_arm())

    baseline_trace = result.baseline.configuration
    topology = result.arm("no-topology")
    assert topology is not None

    moved = {key for key in baseline_trace if baseline_trace[key] != topology.configuration[key]}
    assert moved == {"topology_enabled"}


async def test_an_arm_that_raises_is_reported_rather_than_ending_the_suite() -> None:
    """One broken arm must not cost the other eight runs."""

    async def explode(subject: Scenario, switches: MechanismSwitches, attempt: int) -> Observation:
        if not switches.enabled("masking"):
            raise RuntimeError("the masking arm could not be configured")
        return observation(correct=True, wandered=False)

    result = await run_ablation(CORPUS, arm=explode)

    broken = result.arm("no-masking")
    assert broken is not None
    assert broken.failure
    assert "could not be configured" in broken.failure
    assert result.baseline.suite.attempts == len(CORPUS)


async def test_only_the_arms_a_configuration_names_are_run() -> None:
    """A full ablation costs nine suite runs; a targeted question should not."""
    result = await run_ablation(
        CORPUS,
        arm=policy_arm(),
        configs=(baseline_config(), AblationConfig(name="no-graph", disabled=("topology",))),
    )

    assert tuple(arm.config.name for arm in result.arms) == (BASELINE_ARM, "no-graph")


# -- the report (T026, T027, T028, SC-003) -------------------------------------


async def measured(**kwargs: object) -> AblationResult:
    """Return a full ablation over the corpus with the given arm behaviour."""
    return await run_ablation(CORPUS, arm=policy_arm(**kwargs), attempts=4)  # type: ignore[arg-type]


async def test_the_report_quantifies_each_mechanism_per_axis() -> None:
    """SC-003: the number, per mechanism, per axis — not one figure per mechanism."""
    report = report_for(await measured(helps=("memory_read",)))

    memory = report.for_mechanism("memory_read")
    accuracy = next(found for found in memory if found.axis == AXIS_ACCURACY)

    assert accuracy.delta > 0.0, "removing memory made the agent worse, so memory is worth points"
    assert accuracy.baseline_rate > accuracy.ablated_rate

    trajectory = next(found for found in memory if found.axis == AXIS_TRAJECTORY)
    assert trajectory.delta == pytest.approx(0.0), "memory did not move the trajectory axis here"


async def test_the_report_quantifies_each_mechanism_per_difficulty_level() -> None:
    """T026. A mechanism that only helps on hard scenarios has to be readable as such."""
    report = report_for(await measured(helps=("memory_read",)))

    by_level = {
        found.difficulty: found
        for found in report.for_mechanism("memory_read")
        if found.axis == AXIS_ACCURACY and found.difficulty is not None
    }

    assert by_level[1].delta == pytest.approx(0.0), "the easy rung needs no memory"
    assert by_level[3].delta > 0.0, "the hard rung is where it pays"


async def test_the_three_learning_mechanisms_are_all_in_the_report() -> None:
    """SC-003 names memory, strategy, and topology, so all three must be priced."""
    report = report_for(await measured(helps=("memory_read",)))

    for name in ("memory_read", "memory_strategy", "topology"):
        assert report.for_mechanism(name), f"{name} was not priced"


async def test_a_mechanism_whose_removal_improves_results_is_flagged() -> None:
    """FR-015. The finding the harness is most valuable for, and easiest to bury."""
    report = report_for(await measured(harms=("knowledge_base",)))

    harmful = {found.mechanism for found in report.harmful}
    assert "knowledge_base" in harmful

    text = report.render()
    assert "HARMFUL" in text
    assert text.index("HARMFUL") < text.index("contribution"), (
        "a harm flag below the table is a harm flag nobody reads"
    )


async def test_a_mechanism_that_changes_nothing_is_reported_as_no_measurable_effect() -> None:
    """A zero is a result. Dressing one up as a percentage point is how a table stops being trusted."""
    report = report_for(await measured(helps=("memory_read",)))

    subagents = [found for found in report.for_mechanism("subagents") if found.difficulty is None]
    assert subagents
    assert all(not found.measurable for found in subagents)
    assert not report.harmful


async def test_the_report_round_trips_and_names_the_arms_it_came_from() -> None:
    """A published number has to carry the experiment that produced it."""
    report = report_for(await measured(helps=("memory_read",)))
    record = report.to_record()

    assert record["arms"]
    assert AblationReport.from_record(record) == report


async def test_an_arm_that_failed_is_not_silently_priced_at_zero() -> None:
    """A broken arm reporting "no measurable effect" would be the worst outcome."""

    async def explode(subject: Scenario, switches: MechanismSwitches, attempt: int) -> Observation:
        if not switches.enabled("seed_calls"):
            raise RuntimeError("no")
        return observation(correct=True, wandered=False)

    report = report_for(await run_ablation(CORPUS, arm=explode))

    assert report.for_mechanism("seed_calls") == ()
    assert "seed_calls" in report.unmeasured
    assert "seed_calls" in report.render()


async def test_configurations_naming_several_mechanisms_are_priced_as_one_arm() -> None:
    """The pre-memory baseline is one experiment, not two subtractions."""
    result = await run_ablation(
        CORPUS,
        arm=policy_arm(helps=("memory_read",)),
        configs=(
            baseline_config(),
            AblationConfig(name="no-learning", disabled=("memory_read", "memory_strategy")),
        ),
        attempts=4,
    )
    report = report_for(result)

    combined = [found for found in report.contributions if found.arm == "no-learning"]
    assert combined
    assert {found.mechanism for found in combined} == {"memory_read+memory_strategy"}


async def test_the_default_suite_is_the_one_the_plan_draws() -> None:
    """Nine arms, baseline first, one mechanism each."""
    assert tuple(found.name for found in one_at_a_time()[1:]) == tuple(
        f"no-{name.replace('_', '-')}" for name in ABLATION_MECHANISMS
    )
