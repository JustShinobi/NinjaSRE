"""The named datasets: what each declares, how one composes from another, and the budgets.

The composition matters as much as the contents. ``degraded`` holds no fixture
files at all — it is ``populated`` plus a declaration of which endpoints
misbehave — and if that stopped working the honest alternative would be forty
duplicated files that drift.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from config.constants.fixtures import (
    FIXTURE_COMMITTED_BYTES_BUDGET,
    FIXTURE_SCENARIO_LOAD_BUDGET_SECONDS,
    FIXTURE_SCENARIO_NAMES,
    SCALE_CONFIG_NODE_COUNT,
    SCALE_EVENT_COUNT,
    SCALE_RESOURCE_COUNT,
    SCALE_RUN_COUNT,
)
from tools.mockplane import scenarios
from tools.mockplane.dataset.scale import config_nodes, events, resources, runs
from tools.mockplane.paths import fixture_root, scenario_dir
from tools.mockplane.scenarios import EVERY_ENDPOINT, Manifest, Override, ScenarioError

pytestmark = pytest.mark.unit


def test_the_manifest_declares_exactly_the_scenarios_the_constants_name() -> None:
    assert Manifest.load().names() == FIXTURE_SCENARIO_NAMES


def test_every_scenario_says_what_it_is_for() -> None:
    missing = [entry.name for entry in Manifest.load() if len(entry.description) < 40]
    assert not missing, f"a scenario nobody can tell the purpose of: {missing}"


def test_every_declared_scenario_loads() -> None:
    for name in FIXTURE_SCENARIO_NAMES:
        assert scenarios.load(name).records, f"{name} loaded nothing"


def test_an_undeclared_scenario_is_refused_and_lists_the_ones_that_exist() -> None:
    with pytest.raises(ScenarioError) as failure:
        scenarios.load("does-not-exist")
    assert "populated" in str(failure.value)


def test_a_derived_scenario_starts_from_its_base() -> None:
    populated = scenarios.load("populated")
    restricted = scenarios.load("restricted")
    assert populated.slugs() <= restricted.slugs()


def test_a_derived_scenario_overrides_only_what_it_declares() -> None:
    populated = scenarios.load("populated")
    restricted = scenarios.load("restricted")
    assert restricted.lookup("principal", {}) != populated.lookup("principal", {})
    assert restricted.lookup("runs", {}) == populated.lookup("runs", {})


def test_the_restricted_scenario_signs_in_as_somebody_who_may_not_act() -> None:
    principal = scenarios.load("restricted").lookup("principal", {})
    assert principal is not None
    assert principal.body["roles"] == ["viewer"]
    assert "remediation.approve" not in principal.body["permissions"]
    assert "investigation.read" in principal.body["permissions"]


def test_the_degraded_scenario_holds_no_files_of_its_own() -> None:
    assert scenarios.scenario_files("degraded") == (), (
        "degraded has grown fixture files; it is populated plus a declaration of "
        "which endpoints misbehave, and duplicating the data is how the two drift"
    )


def test_the_degraded_scenario_declares_every_kind_of_failure() -> None:
    degraded = Manifest.load().get("degraded")
    declared = degraded.overrides
    assert any(item.status == 500 for item in declared), "nothing answers 500"
    assert any(item.status == 403 for item in declared), "nothing answers 403"
    assert any(item.status == 404 for item in declared), "nothing answers 404"
    assert any(item.latency_ms > 0 for item in declared), "nothing is slow"
    assert any(item.refuse for item in declared), "nothing refuses the connection"
    assert any(item.truncate for item in declared), "nothing answers a truncated body"
    assert any(item.empty for item in declared), "nothing answers empty"


def test_an_override_governs_the_endpoint_it_names_and_no_other() -> None:
    degraded = Manifest.load().get("degraded")
    assert degraded.override_for("incidents") is not None
    assert degraded.override_for("runs") is None


def test_a_scenario_composes_with_a_per_endpoint_override_at_run_time() -> None:
    composed = Manifest.load().get("populated").with_override(Override(slug="runs", status=500))
    override = composed.override_for("runs")
    assert override is not None and override.status == 500


def test_an_override_naming_every_endpoint_governs_one_that_declares_nothing() -> None:
    composed = (
        Manifest.load().get("populated").with_override(Override(slug=EVERY_ENDPOINT, latency_ms=50))
    )
    assert composed.override_for("audit-events") is not None


def test_a_more_specific_override_wins_over_the_catch_all() -> None:
    composed = (
        Manifest.load()
        .get("populated")
        .with_override(Override(slug=EVERY_ENDPOINT, latency_ms=50))
        .with_override(Override(slug="runs", status=500))
    )
    override = composed.override_for("runs")
    assert override is not None and override.status == 500


def test_the_empty_scenario_answers_the_contract_shape_with_nothing_in_it() -> None:
    empty = scenarios.load("empty")
    runs_record = empty.lookup("runs", {})
    assert runs_record is not None
    assert runs_record.body == {"runs": []}, "an empty state that answered {} is not an empty state"


def test_the_empty_scenario_answers_a_detail_read_with_absence_not_an_empty_object() -> None:
    detail = scenarios.load("empty").lookup("run-detail", {"run_id": "run-0001"})
    assert detail is not None
    assert detail.status == 404


def test_the_first_run_scenario_is_configured_and_not_finished() -> None:
    health = scenarios.load("first-run").lookup("health", {})
    assert health is not None
    assert health.body["ready"] is False
    assert health.body["reasons"], "a checklist with nothing on it is not a checklist"


def test_the_live_scenario_carries_a_run_in_flight() -> None:
    stream = scenarios.load("incident-live").lookup("run-stream", {"run_id": "run-0003"})
    assert stream is not None
    assert len(stream.body["events"]) > len(
        scenarios.load("populated").lookup("run-stream", {"run_id": "run-0003"}).body["events"]
    )


# --- The generated scenario -------------------------------------------------------


def test_the_scale_scenario_is_generated_rather_than_committed() -> None:
    assert scenarios.scenario_files("scale") == ()
    assert Manifest.load().get("scale").generated is True


def test_the_scale_scenario_holds_the_declared_volumes() -> None:
    assert len(runs()) == SCALE_RUN_COUNT
    assert len(resources()) == SCALE_RESOURCE_COUNT
    assert len(events()) == SCALE_EVENT_COUNT
    assert len(config_nodes()) == SCALE_CONFIG_NODE_COUNT


def test_the_scale_scenario_is_the_same_deployment_with_more_in_it() -> None:
    identifiers = {run["run_id"] for run in runs()}
    assert "run-0001" in identifiers, "the declared runs were renumbered out of existence"


def test_generating_it_twice_gives_the_same_thing() -> None:
    assert [run["run_id"] for run in runs()] == [run["run_id"] for run in runs()]


# --- Budgets ----------------------------------------------------------------------


@pytest.mark.benchmark
def test_loading_any_scenario_stays_within_its_budget() -> None:
    for name in FIXTURE_SCENARIO_NAMES:
        started = time.perf_counter()
        scenarios.load(name)
        elapsed = time.perf_counter() - started
        assert elapsed < FIXTURE_SCENARIO_LOAD_BUDGET_SECONDS, (
            f"loading {name} took {elapsed:.2f}s, over the budget the console's "
            f"development loop is allowed to wait"
        )


def test_the_committed_dataset_stays_within_its_size_budget() -> None:
    total = sum(path.stat().st_size for path in fixture_root().rglob("*") if path.is_file())
    assert total < FIXTURE_COMMITTED_BYTES_BUDGET, (
        f"the committed fixture tree is {total} bytes, over budget; the scale "
        f"scenario is generated for exactly this reason"
    )


def test_no_scenario_directory_exists_for_a_scenario_the_manifest_does_not_declare() -> None:
    root = fixture_root() / "scenarios"
    declared = set(FIXTURE_SCENARIO_NAMES)
    stray = [path.name for path in root.iterdir() if path.is_dir() and path.name not in declared]
    assert not stray, f"fixture directories nothing declares: {stray}"


def test_a_fixture_naming_an_endpoint_that_no_longer_exists_fails_the_load(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"default": "x", "scenarios": [{"name": "x", "description": "a test"}]}',
        encoding="utf-8",
    )
    directory = scenario_dir("x", tmp_path)
    directory.mkdir(parents=True)
    (directory / "gone.json").write_text('{"slug": "gone", "responses": []}', encoding="utf-8")
    with pytest.raises(ScenarioError) as failure:
        scenarios.load("x", tmp_path)
    assert "gone" in str(failure.value)
