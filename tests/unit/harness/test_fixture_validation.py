"""SC-003: a malformed fixture fails to load, naming the file and the field.

The whole point of a typed fixture schema is that a mistake is caught at load
time by a message that says where it is. "KeyError: 'severity'" during a suite
run is a fixture schema that exists on paper: it tells the author that
something is missing without telling them which of forty scenarios it is
missing from.

So every test here breaks exactly one thing and asserts on two properties of
the failure: the file it names and the field it names. Anything else about the
wording is free to change.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.harness.loader import load_scenario
from tests.harness.schemas import FixtureError
from tests.unit.harness.conftest import (
    VALID_ANSWER,
    VALID_EVIDENCE,
    VALID_SCENARIO,
    ScenarioWriter,
)

pytestmark = pytest.mark.unit


def _scenario(**overrides: Any) -> dict[str, Any]:
    document = dict(VALID_SCENARIO)
    document.update(overrides)
    return {key: value for key, value in document.items() if value is not None}


def _answer(**overrides: Any) -> dict[str, Any]:
    document = dict(VALID_ANSWER)
    document.update(overrides)
    return {key: value for key, value in document.items() if value is not None}


def _evidence(**overrides: Any) -> dict[str, Mapping[str, Any]]:
    document: dict[str, Any] = dict(VALID_EVIDENCE)
    document.update(overrides)
    return {"kubernetes.json": {key: value for key, value in document.items() if value is not None}}


def _failure(directory: Path) -> FixtureError:
    with pytest.raises(FixtureError) as raised:
        load_scenario(directory)
    return raised.value


# -- scenario.yml -------------------------------------------------------------


def test_a_missing_scenario_field_names_the_file_and_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=_scenario(severity=None)))

    assert error.field == "severity"
    assert error.path.name == "scenario.yml"
    assert "scenario.yml" in str(error)
    assert "severity" in str(error)


def test_an_invented_failure_mode_is_a_load_error_rather_than_a_silent_mismatch(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=_scenario(failure_mode="thundering_herd")))

    assert error.field == "failure_mode"
    assert "thundering_herd" in str(error)


def test_a_difficulty_outside_the_curriculum_is_refused(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=_scenario(scenario_difficulty=7)))

    assert error.field == "scenario_difficulty"
    assert error.path.name == "scenario.yml"


def test_an_unknown_schema_version_is_refused_rather_than_read_on_a_guess(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=_scenario(schema_version="9")))

    assert error.field == "schema_version"


def test_an_evidence_source_no_integration_provides_is_a_load_error(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=_scenario(available_evidence=["kubernetezz"])))

    assert error.field == "available_evidence"
    assert "kubernetezz" in str(error)


def test_an_invented_adversarial_signal_is_a_load_error(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(
        write_scenario(
            scenario=_scenario(scenario_difficulty=2, adversarial_signals=["vibes_were_off"])
        )
    )

    assert error.field == "adversarial_signals"


def test_a_confounded_level_declaring_no_confounder_is_mislabelled_and_says_so(
    write_scenario: ScenarioWriter,
) -> None:
    """FR-022: level 2 *means* one planted confounder, so silence is a defect."""
    error = _failure(write_scenario(scenario=_scenario(scenario_difficulty=2)))

    assert error.field == "adversarial_signals"


def test_unparseable_yaml_names_the_file_it_could_not_read(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(raw_scenario="scenario_id: [unclosed\n"))

    assert error.path.name == "scenario.yml"


def test_a_scenario_directory_with_no_manifest_names_the_missing_file(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(scenario=None))

    assert error.path.name == "scenario.yml"


# -- alert.json ---------------------------------------------------------------


def test_an_alert_with_neither_payload_nor_text_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(alert={"received_at": "2026-08-07T12:30:00+00:00"}))

    assert error.path.name == "alert.json"
    assert error.field in {"payload", "text"}


def test_a_missing_alert_names_the_file(write_scenario: ScenarioWriter) -> None:
    error = _failure(write_scenario(alert=None))

    assert error.path.name == "alert.json"


def test_an_alert_payload_of_the_wrong_type_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(alert={"payload": "not a mapping"}))

    assert error.field == "payload"


# -- evidence fixtures --------------------------------------------------------


def test_an_evidence_fixture_with_no_responses_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(evidence=_evidence(responses=None)))

    assert error.path.name == "kubernetes.json"
    assert error.field == "responses"


def test_a_recorded_response_with_a_non_numeric_status_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    broken = {"match": {"path_contains": "/events"}, "status": "OK", "body": {}}
    error = _failure(write_scenario(evidence=_evidence(responses=[broken])))

    assert error.field.endswith("status")


def test_an_evidence_fixture_naming_an_unknown_integration_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(evidence=_evidence(integration="kuberneetes")))

    assert error.field == "integration"


# -- answer.yml ---------------------------------------------------------------


def test_a_missing_root_cause_category_names_the_file_and_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(answer=_answer(root_cause_category=None)))

    assert error.path.name == "answer.yml"
    assert error.field == "root_cause_category"


def test_a_root_cause_category_outside_the_taxonomy_is_refused(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(answer=_answer(root_cause_category="cosmic_rays")))

    assert error.field == "root_cause_category"
    assert "cosmic_rays" in str(error)


def test_an_answer_with_no_required_keywords_is_refused(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(answer=_answer(required_keywords=[])))

    assert error.field == "required_keywords"


def test_a_missing_model_response_names_the_field(write_scenario: ScenarioWriter) -> None:
    error = _failure(write_scenario(answer=_answer(model_response=None)))

    assert error.field == "model_response"


def test_a_trajectory_action_no_capability_declares_is_a_load_error(
    write_scenario: ScenarioWriter,
) -> None:
    """FR-005: a renamed capability breaks the build, not the score."""
    error = _failure(write_scenario(answer=_answer(optimal_trajectory=["list_pods_v2"])))

    assert error.field == "optimal_trajectory"
    assert "list_pods_v2" in str(error)


def test_a_golden_trajectory_action_no_capability_declares_is_a_load_error(
    write_scenario: ScenarioWriter,
) -> None:
    golden = {"ordered_actions": ["kubernetes_workload_events", "get_pod_logs"]}
    error = _failure(write_scenario(answer=_answer(golden_trajectory=golden)))

    assert error.field.startswith("golden_trajectory")
    assert "get_pod_logs" in str(error)


def test_an_unknown_golden_matching_strategy_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    golden = {"ordered_actions": ["kubernetes_workload_events"], "matching": "vibes"}
    error = _failure(write_scenario(answer=_answer(golden_trajectory=golden)))

    assert error.field.endswith("matching")


def test_a_forbidden_category_outside_the_taxonomy_names_the_field(
    write_scenario: ScenarioWriter,
) -> None:
    error = _failure(write_scenario(answer=_answer(forbidden_categories=["gremlins"])))

    assert error.field == "forbidden_categories"


def test_a_loop_ceiling_above_the_constitutional_bound_is_refused(
    write_scenario: ScenarioWriter,
) -> None:
    """Article II: the answer key may lower the ceiling, never raise it."""
    error = _failure(write_scenario(answer=_answer(max_investigation_loops=500)))

    assert error.field == "max_investigation_loops"


def test_a_required_evidence_source_outside_the_declared_ones_is_refused(
    write_scenario: ScenarioWriter,
) -> None:
    """An answer key demanding evidence the scenario cannot serve is unsatisfiable."""
    error = _failure(write_scenario(answer=_answer(required_evidence_sources=["datadog"])))

    assert error.field == "required_evidence_sources"
