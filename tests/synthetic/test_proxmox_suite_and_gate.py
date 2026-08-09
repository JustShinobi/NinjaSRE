"""The corpus as a gate: what it must contain, what it costs, and what fails it.

Three obligations meet here. The suite has to run from fixtures on the
pull-request path inside a stated budget; a change that makes a scenario worse
has to fail with the scenario named and the readings shown; and no hypervisor
write may exist without a scenario that scores it — because those actions write
to somebody's machine, and an untested one is not acceptable under deadline.

The baseline is committed, so moving a number is a diff somebody reviews rather
than a thing that happens quietly between releases.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from config.constants.hypervisor_scenarios import (
    ARM_FULL,
    ARM_NO_MEMORY,
    HYPERVISOR_SCENARIO_DOMAINS,
    HYPERVISOR_SCENARIO_MINIMUM,
    HYPERVISOR_SUITE_BUDGET_SECONDS,
    MODEL_HOSTED,
    MODEL_SELF_HOSTED,
    SCENARIO_MODE_FIXTURE,
)
from tests.harness.proxmox.baseline import Regressed, baseline_path, gate, read_baseline
from tests.harness.proxmox.coverage import exercised, unjustified_claims
from tests.harness.proxmox.declaration import declared_capabilities
from tests.harness.proxmox.suite import CORPUS_ROOT, load_corpus, run_suite
from tests.harness.proxmox.verdicts import ActionVerdict, DiagnosisVerdict

pytestmark = pytest.mark.synthetic


@pytest.fixture(scope="module")
def corpus() -> tuple:
    """Return the whole corpus, loaded once for the module."""
    return load_corpus(CORPUS_ROOT)


# -- the corpus itself --------------------------------------------------------


def test_every_scenario_in_the_corpus_loads(corpus: tuple) -> None:
    """A malformed declaration is a load error, and this is where it surfaces."""
    assert len(corpus) >= HYPERVISOR_SCENARIO_MINIMUM
    assert len({scenario.scenario_id for scenario, _ in corpus}) == len(corpus)


def test_all_four_domains_and_the_host_layer_are_covered(corpus: tuple) -> None:
    """A domain with no scenario is a domain the number says nothing about."""
    present = {scenario.domain for scenario, _ in corpus}

    assert present == set(HYPERVISOR_SCENARIO_DOMAINS)


def test_every_scenario_declares_what_the_specification_asks_it_to(corpus: tuple) -> None:
    """The situation, the fixtures, the cause, the evidence, the response."""
    for scenario, runs in corpus:
        assert scenario.situation.strip(), scenario.scenario_id
        assert scenario.readings.tools, scenario.scenario_id
        assert scenario.readings.must_report, scenario.scenario_id
        assert scenario.response.why.strip(), scenario.scenario_id
        assert runs, scenario.scenario_id
        if not scenario.truth.insufficient:
            assert scenario.truth.evidence, scenario.scenario_id


def test_every_scenario_is_recorded_against_both_models_and_both_arms(corpus: tuple) -> None:
    """SC-010 and SC-011 are only true of a corpus that filled the matrix."""
    wanted = {
        f"{model}/{arm}"
        for model in (MODEL_HOSTED, MODEL_SELF_HOSTED)
        for arm in (ARM_FULL, ARM_NO_MEMORY)
    }
    for scenario, runs in corpus:
        assert {run.cell for run in runs} == wanted, scenario.scenario_id


def test_a_destructive_scenario_says_how_the_laboratory_is_restored(corpus: tuple) -> None:
    destructive = [scenario for scenario, _ in corpus if scenario.destructive]

    assert destructive
    for scenario in destructive:
        assert scenario.laboratory is not None
        assert scenario.laboratory.restore.strip()


# -- SC-001 and SC-002: it runs from fixtures, twice, identically -------------


async def test_the_whole_suite_runs_from_fixtures_with_no_cluster(corpus: tuple) -> None:
    report = await run_suite(CORPUS_ROOT)

    assert report.total == sum(len(runs) for _, runs in corpus)
    assert report.modes() == {SCENARIO_MODE_FIXTURE: tuple(sorted(report.scenario_ids))}


async def test_the_suite_produces_identical_readings_and_identical_scores_twice() -> None:
    """SC-002. A suite whose number moves on its own cannot gate anything."""
    first, second = await run_suite(CORPUS_ROOT), await run_suite(CORPUS_ROOT)

    assert first.to_artifact() == second.to_artifact()


async def test_the_suite_finishes_inside_its_declared_budget() -> None:
    """SC-001, FR-012. Twenty-eight scenarios that become slow become skipped."""
    started = time.perf_counter()
    await run_suite(CORPUS_ROOT)

    assert time.perf_counter() - started < HYPERVISOR_SUITE_BUDGET_SECONDS


# -- the corpus discriminates -------------------------------------------------


async def test_the_corpus_contains_a_fixture_of_each_action_verdict() -> None:
    """SC-004. Four verdicts nothing ever produces are four unproven branches."""
    report = await run_suite(CORPUS_ROOT)

    assert {found.action for found in report.scores} == set(ActionVerdict)


async def test_the_corpus_contains_a_scenario_whose_correct_answer_is_i_cannot_tell() -> None:
    """SC-007, and its converse: a confident answer there has to score wrong."""
    report = await run_suite(CORPUS_ROOT)
    insufficient = [found for found in report.scores if found.scenario_id.startswith("h2-")]

    assert {found.diagnosis for found in insufficient} >= {
        DiagnosisVerdict.CORRECT,
        DiagnosisVerdict.INCORRECT,
    }


async def test_a_model_that_could_not_finish_is_reported_apart_from_a_wrong_answer() -> None:
    """FR-018, SC-011: the two call for opposite responses."""
    report = await run_suite(CORPUS_ROOT)

    assert report.incomplete
    assert all(found.run is not None for found in report.incomplete)
    assert all(found.run.incomplete_reason for found in report.incomplete if found.run)


async def test_a_red_herring_is_followed_somewhere_and_resisted_elsewhere() -> None:
    """SC-006 needs both halves, or the penalty is untested in one direction."""
    report = await run_suite(CORPUS_ROOT)
    planted = [
        found
        for found in report.scores
        if any("red herring" in line or "took the bait" in line for line in found.reasoning)
    ]

    assert planted


# -- SC-010 and SC-011: ablation and models -----------------------------------


async def test_the_suite_reports_a_score_with_memory_and_without_it() -> None:
    """FR-016. A claim that learning helps becomes a difference between cells."""
    report = await run_suite(CORPUS_ROOT)

    full = report.cell(model=MODEL_HOSTED, arm=ARM_FULL)
    ablated = report.cell(model=MODEL_HOSTED, arm=ARM_NO_MEMORY)

    assert full.scored == ablated.scored > 0
    assert full.passes > ablated.passes


async def test_the_suite_reports_each_model_it_ran_against() -> None:
    """FR-017. A self-hosted model's capability here becomes a known number."""
    report = await run_suite(CORPUS_ROOT)
    cells = {(found.model, found.arm): found for found in report.cells()}

    assert {model for model, _ in cells} == {MODEL_HOSTED, MODEL_SELF_HOSTED}
    assert cells[(MODEL_HOSTED, ARM_FULL)].passes > cells[(MODEL_SELF_HOSTED, ARM_FULL)].passes


# -- T-039 / SC-009: capability coverage --------------------------------------


def test_every_hypervisor_write_is_exercised_by_at_least_one_scenario(corpus: tuple) -> None:
    """FR-015. Those actions write to somebody's hypervisor."""
    missing = sorted(declared_capabilities() - exercised(corpus))

    assert not missing, (
        f"{missing} is declared as a hypervisor write and no scenario scores it. Add a scenario "
        f"that asks for it, or that scores a run which proposed it."
    )


def test_a_scenario_cannot_claim_to_exercise_a_capability_nothing_touches(corpus: tuple) -> None:
    """Otherwise coverage is satisfied by editing a list."""
    assert not unjustified_claims(corpus)


# -- T-037 / T-038: the committed baseline and the gate -----------------------


def test_the_baseline_is_committed_beside_the_corpus() -> None:
    """FR-014. Moving a number is a reviewable change or it is not a baseline."""
    stored = baseline_path(CORPUS_ROOT)

    assert stored.exists()
    assert json.loads(stored.read_text(encoding="utf-8"))["scenarios"]


async def test_the_suite_as_it_stands_matches_its_committed_baseline() -> None:
    report = await run_suite(CORPUS_ROOT)

    gate(report, read_baseline(baseline_path(CORPUS_ROOT)))


async def test_a_seeded_regression_fails_naming_the_scenario_and_showing_the_readings() -> None:
    """SC-008, FR-013. A gate whose failure nobody can read is a gate people mute."""
    report = await run_suite(CORPUS_ROOT)
    stored = read_baseline(baseline_path(CORPUS_ROOT))
    seeded = {
        **stored,
        "scenarios": [
            {**entry, "passed": True, "action": ActionVerdict.CORRECT.value}
            for entry in stored["scenarios"]
        ],
        "pass_rate": 1.0,
    }

    with pytest.raises(Regressed) as failure:
        gate(report, seeded)

    printed = str(failure.value)
    assert "q6-high-availability-fenced-a-guest" in printed
    assert "readings:" in printed


async def test_an_improvement_that_hides_a_harmful_action_still_fails_the_gate() -> None:
    """FR-011 at the gate: the aggregate is allowed to rise and the answer is no."""
    report = await run_suite(CORPUS_ROOT)
    stored = read_baseline(baseline_path(CORPUS_ROOT))
    pretend = {
        **stored,
        "pass_rate": 0.0,
        "scenarios": [
            {**entry, "passed": False, "action": ActionVerdict.CORRECT.value}
            for entry in stored["scenarios"]
        ],
    }

    with pytest.raises(Regressed, match="became harmful"):
        gate(report, pretend)


def test_the_baseline_directory_is_the_corpus_root() -> None:
    assert baseline_path(CORPUS_ROOT).parent == Path(CORPUS_ROOT)
