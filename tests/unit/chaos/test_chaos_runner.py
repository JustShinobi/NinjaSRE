"""The full cycle, fourteen times, and the distinction that makes it worth running.

Every experiment has to inject, alert, investigate, score, and clean up. The
one that did not produce its symptom has to be reported as an invalid
experiment rather than as an agent failure. The second is the harder
claim and the more valuable one: without it the suite has fourteen numbers and
no way to say which of them measured anything.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from config.constants.chaos import CHAOS_EXPERIMENT_IDS
from config.constants.evaluation import SCORING_AXES
from tests.chaos.framework.catalogue import EXPERIMENTS_ROOT, discover_experiments
from tests.chaos.framework.lock import ClusterBusy
from tests.chaos.framework.recorded import RecordedCluster
from tests.chaos.runner import expectation_of, run_experiment, run_suite
from tests.harness.realruns import RunValidity
from tests.support.investigators import (
    DerivedInvestigator,
    ScriptedInvestigator,
    correct_answer,
    wrong_answer,
)

EXPERIMENTS = discover_experiments(EXPERIMENTS_ROOT)


def _ticking(step: float = 25.0) -> object:
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


def _cluster_seeing_every_symptom() -> RecordedCluster:
    """Return a cluster on which every experiment's probe reports its symptom."""
    readings: dict[str, list[list[str]]] = {}
    for experiment in EXPERIMENTS:
        probe = experiment.expectation.validity_probe.check
        readings.setdefault(probe, []).append(list(experiment.expectation.expected_symptom))
    # One reading per probe, holding every symptom any experiment using it
    # declares, because the recorded cluster answers a probe by name.
    return RecordedCluster(
        readings={
            probe: [sorted({symptom for entry in entries for symptom in entry})]
            for probe, entries in readings.items()
        }
    )


def _probe_options() -> dict[str, object]:
    return {"sleep": lambda _: None, "clock": _ticking()}


# --- the whole cycle, fourteen times -----------------------------------------


async def test_every_experiment_injects_alerts_investigates_scores_and_cleans_up(
    tmp_path: Path,
) -> None:
    cluster = _cluster_seeing_every_symptom()
    investigator = DerivedInvestigator(
        expectations={
            experiment.experiment_id: expectation_of(experiment) for experiment in EXPERIMENTS
        },
        answer=correct_answer,
    )

    report, outcomes = await run_suite(
        EXPERIMENTS,
        cluster=cluster,
        investigator=investigator,
        run_id="r1",
        lock_root=tmp_path,
        **_probe_options(),
    )

    assert len(outcomes) == len(CHAOS_EXPERIMENT_IDS)
    for outcome in outcomes:
        assert outcome.ran, f"{outcome.experiment_id}: {outcome.refused}"
        assert outcome.validity is not None and outcome.validity.valid, outcome.experiment_id
        assert outcome.score is not None and outcome.score.scored, outcome.experiment_id
        assert outcome.cleanup.clean, outcome.experiment_id
    assert cluster.active_faults() == ()
    assert len(report.scored) == len(CHAOS_EXPERIMENT_IDS)
    assert report.pass_rate == 1.0


async def test_the_alert_the_pipeline_receives_names_the_fault_that_raised_it(
    tmp_path: Path,
) -> None:
    """The run is entered through the alert, not through a bare objective."""
    cluster = _cluster_seeing_every_symptom()
    investigator = DerivedInvestigator(
        expectations={
            experiment.experiment_id: expectation_of(experiment) for experiment in EXPERIMENTS
        },
        answer=correct_answer,
    )

    await run_suite(
        EXPERIMENTS[:3],
        cluster=cluster,
        investigator=investigator,
        run_id="r1",
        lock_root=tmp_path,
        **_probe_options(),
    )

    assert len(investigator.alerts) == 3
    for alert in investigator.alerts:
        entry = alert.payload["alerts"][0]
        assert entry["labels"]["ninjasre_fault"].endswith("-r1")


# --- the evaluation harness's five axes, unchanged ---------------------------


async def test_a_real_run_is_scored_on_the_same_five_axes_as_a_synthetic_one(
    tmp_path: Path,
) -> None:
    experiment = EXPERIMENTS[0]
    cluster = RecordedCluster(
        readings={
            experiment.expectation.validity_probe.check: [
                list(experiment.expectation.expected_symptom)
            ]
        }
    )

    outcome = await run_experiment(
        experiment,
        cluster=cluster,
        investigator=ScriptedInvestigator([correct_answer(expectation_of(experiment))]),
        run_id="r1",
        **_probe_options(),
    )

    assert outcome.score is not None and outcome.score.score is not None
    assert tuple(axis.name for axis in outcome.score.score.axes) == SCORING_AXES


# --- an invalid experiment is not an agent failure ---------------------------


async def test_an_experiment_that_never_bit_is_reported_not_scored(tmp_path: Path) -> None:
    experiment = EXPERIMENTS[0]
    cluster = RecordedCluster(readings={experiment.expectation.validity_probe.check: [[]]})

    outcome = await run_experiment(
        experiment,
        cluster=cluster,
        # The agent would have been wrong; the point is that nobody finds out,
        # because the fault it was asked about never happened.
        investigator=ScriptedInvestigator([wrong_answer(expectation_of(experiment))]),
        run_id="r1",
        **_probe_options(),
    )

    assert outcome.score is not None
    assert outcome.score.validity is RunValidity.UNKNOWN
    assert not outcome.score.scored
    assert not outcome.score.agent_failure


async def test_the_report_keeps_agent_failures_and_experiment_failures_apart(
    tmp_path: Path,
) -> None:
    """ "Four failed" is not a sentence until it says how many were the agent."""
    bit, missed = EXPERIMENTS[0], EXPERIMENTS[1]
    cluster = RecordedCluster(
        readings={
            bit.expectation.validity_probe.check: [list(bit.expectation.expected_symptom)],
            missed.expectation.validity_probe.check: [["something_unrelated"]],
        }
    )
    investigator = DerivedInvestigator(
        expectations={
            experiment.experiment_id: expectation_of(experiment) for experiment in (bit, missed)
        },
        answer=wrong_answer,
    )

    report, _ = await run_suite(
        (bit, missed),
        cluster=cluster,
        investigator=investigator,
        run_id="r1",
        lock_root=tmp_path,
        **_probe_options(),
    )

    assert [run.key for run in report.agent_failures] == [f"chaos/{bit.experiment_id}"]
    assert [run.key for run in report.experiment_failures] == [f"chaos/{missed.experiment_id}"]
    assert "The experiment failed, not the agent" in report.render()


# --- refusals ----------------------------------------------------------------


async def test_an_unhealthy_cluster_refuses_the_experiment_before_injecting(
    tmp_path: Path,
) -> None:
    experiment = EXPERIMENTS[0]
    cluster = RecordedCluster(unhealthy_pods=("payments-1",))

    outcome = await run_experiment(
        experiment,
        cluster=cluster,
        investigator=ScriptedInvestigator([correct_answer(expectation_of(experiment))]),
        run_id="r1",
        **_probe_options(),
    )

    assert not outcome.ran
    assert "already unhealthy" in outcome.refused
    assert cluster.applied == []


async def test_a_second_suite_against_the_same_cluster_is_refused(tmp_path: Path) -> None:
    from tests.chaos.framework.lock import cluster_lock

    cluster = _cluster_seeing_every_symptom()
    with (
        cluster_lock(cluster.name, root=tmp_path, run_id="already-running"),
        pytest.raises(ClusterBusy),
    ):
        await run_suite(
            EXPERIMENTS[:1],
            cluster=cluster,
            investigator=ScriptedInvestigator([correct_answer(expectation_of(EXPERIMENTS[0]))]),
            run_id="second",
            lock_root=tmp_path,
            **_probe_options(),
        )
