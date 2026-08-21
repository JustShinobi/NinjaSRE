"""Discovery, loading, and inheritance — the part that makes SC-005 true.

Adding a scenario has to be adding a directory. So discovery walks rather than
reads a list, inheritance lets a family of scenarios state only what differs,
and everything a scenario declares is resolved into one value the runner can
take. If any of that needed a code change per scenario, the corpus would grow
at the speed of the harness rather than at the speed of the fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.harness.loader import discover_scenarios, load_scenario
from tests.harness.schemas import FixtureError
from tests.unit.harness.conftest import VALID_ANSWER, VALID_SCENARIO, ScenarioWriter

pytestmark = pytest.mark.unit


def _base_family(root: Path) -> None:
    """Write a base scenario and a child that overrides only what differs."""
    suite = root / "kubernetes"
    (suite / "000-healthy").mkdir(parents=True)
    (suite / "004-liveness-probe").mkdir(parents=True)

    base: dict[str, Any] = dict(VALID_SCENARIO)
    base.update(scenario_id="000-healthy", failure_mode="none", scenario_difficulty=1)
    (suite / "000-healthy" / "scenario.yml").write_text(yaml.safe_dump(base), encoding="utf-8")
    (suite / "000-healthy" / "answer.yml").write_text(
        yaml.safe_dump(
            {
                "root_cause_category": "healthy",
                "required_keywords": ["healthy"],
                "model_response": "ROOT_CAUSE: nothing is wrong.\n",
            }
        ),
        encoding="utf-8",
    )
    (suite / "000-healthy" / "alert.json").write_text(
        json.dumps({"text": "everything looks fine", "received_at": "2026-08-07T12:30:00+00:00"}),
        encoding="utf-8",
    )
    (suite / "000-healthy" / "kubernetes.json").write_text(
        json.dumps(
            {
                "integration": "kubernetes",
                "responses": [
                    {
                        "match": {"path_contains": "/events"},
                        "status": 200,
                        "body": {"items": []},
                        "adversarial_signals": ["healthy_replicas_present"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    child = {
        "schema_version": "1",
        "scenario_id": "004-liveness-probe",
        "base": "000-healthy",
        "failure_mode": "probe_misconfiguration",
        "scenario_difficulty": 2,
        "adversarial_signals": ["healthy_replicas_present"],
    }
    (suite / "004-liveness-probe" / "scenario.yml").write_text(
        yaml.safe_dump(child), encoding="utf-8"
    )
    (suite / "004-liveness-probe" / "answer.yml").write_text(
        yaml.safe_dump(
            {
                "root_cause_category": "configuration_error",
                "required_keywords": ["liveness", "probe"],
                "model_response": "ROOT_CAUSE: the liveness probe is killing the container.\n",
            }
        ),
        encoding="utf-8",
    )


def test_a_valid_scenario_loads_into_one_value(write_scenario: ScenarioWriter) -> None:
    scenario = load_scenario(write_scenario())

    assert scenario.scenario_id == "001-oom-kill"
    assert scenario.suite == "kubernetes"
    assert scenario.difficulty == 1
    assert scenario.failure_mode == "memory_exhaustion"
    assert scenario.answer.root_cause_category == "resource_exhaustion"
    assert [fixture.filename for fixture in scenario.evidence] == ["kubernetes.json"]


def test_discovery_walks_rather_than_reading_a_list(
    tmp_path: Path, write_scenario: ScenarioWriter
) -> None:
    """SC-005: the corpus grows by adding a directory, and nothing else."""
    write_scenario(suite="kubernetes", name="001-oom-kill")
    aws = dict(VALID_SCENARIO)
    aws.update(
        scenario_id="002-instance-retirement",
        failure_mode="node_failure",
        available_evidence=["aws_ec2"],
        integrations=["aws_ec2"],
    )
    write_scenario(
        suite="aws",
        name="002-instance-retirement",
        scenario=aws,
        evidence={
            "aws_ec2.json": {
                "integration": "aws_ec2",
                "responses": [
                    {
                        "match": {"path_contains": "DescribeInstanceStatus"},
                        "status": 200,
                        "body": {},
                    }
                ],
            }
        },
    )

    found = discover_scenarios(tmp_path)

    assert [(one.suite, one.scenario_id) for one in found] == [
        ("aws", "002-instance-retirement"),
        ("kubernetes", "001-oom-kill"),
    ]


def test_discovery_ignores_a_directory_that_is_not_a_scenario(
    tmp_path: Path, write_scenario: ScenarioWriter
) -> None:
    write_scenario()
    (tmp_path / "kubernetes" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (tmp_path / "kubernetes" / "README.md").write_text("notes", encoding="utf-8")

    assert len(discover_scenarios(tmp_path)) == 1


def test_a_child_inherits_everything_it_does_not_override(tmp_path: Path) -> None:
    _base_family(tmp_path)

    child = load_scenario(tmp_path / "kubernetes" / "004-liveness-probe")

    assert child.failure_mode == "probe_misconfiguration"
    assert child.difficulty == 2
    assert child.severity == "critical"
    assert child.available_evidence == ("kubernetes",)
    assert child.alert.get("text") == "everything looks fine"
    assert [fixture.filename for fixture in child.evidence] == ["kubernetes.json"]


def test_a_child_overriding_an_evidence_fixture_replaces_it_rather_than_merging(
    tmp_path: Path,
) -> None:
    _base_family(tmp_path)
    (tmp_path / "kubernetes" / "004-liveness-probe" / "kubernetes.json").write_text(
        json.dumps(
            {
                "integration": "kubernetes",
                "responses": [
                    {
                        "match": {"path_contains": "/events"},
                        "status": 200,
                        "body": {"items": [{"reason": "Unhealthy"}]},
                        "adversarial_signals": ["healthy_replicas_present"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    child = load_scenario(tmp_path / "kubernetes" / "004-liveness-probe")

    assert len(child.evidence) == 1
    body = child.evidence[0].responses[0].body
    assert isinstance(body, dict)
    assert body["items"] == [{"reason": "Unhealthy"}]


def test_a_base_that_does_not_exist_names_the_field(tmp_path: Path) -> None:
    _base_family(tmp_path)
    manifest = tmp_path / "kubernetes" / "004-liveness-probe" / "scenario.yml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    document["base"] = "000-imaginary"
    manifest.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(FixtureError) as raised:
        load_scenario(tmp_path / "kubernetes" / "004-liveness-probe")

    assert raised.value.field == "base"
    assert "000-imaginary" in str(raised.value)


def test_a_scenario_inheriting_from_itself_is_refused_rather_than_looping(
    write_scenario: ScenarioWriter,
) -> None:
    scenario = dict(VALID_SCENARIO)
    scenario["base"] = "001-oom-kill"

    with pytest.raises(FixtureError) as raised:
        load_scenario(write_scenario(scenario=scenario))

    assert raised.value.field == "base"


def test_the_answer_key_carries_every_optional_axis_it_declared(
    write_scenario: ScenarioWriter,
) -> None:
    answer = dict(VALID_ANSWER)
    answer.update(
        equivalent_root_cause_categories=["capacity_limit"],
        forbidden_categories=["healthy", "unknown"],
        forbidden_keywords=["disk full"],
        ruling_out_keywords=["no disk pressure"],
        required_evidence_sources=["kubernetes"],
        optimal_trajectory=["kubernetes_workload_events"],
        golden_trajectory={
            "ordered_actions": ["kubernetes_workload_events"],
            "matching": "lcs",
            "max_edit_distance": 1,
            "max_extra_actions": 2,
            "max_redundancy": 0,
        },
        max_investigation_loops=4,
        required_queries=["checkout"],
    )

    key = load_scenario(write_scenario(answer=answer)).answer

    assert key.equivalent_root_cause_categories == ("capacity_limit",)
    assert key.forbidden_categories == ("healthy", "unknown")
    assert key.ruling_out_keywords == ("no disk pressure",)
    assert key.required_evidence_sources == ("kubernetes",)
    assert key.optimal_trajectory == ("kubernetes_workload_events",)
    assert key.golden_trajectory is not None
    assert key.golden_trajectory.matching == "lcs"
    assert key.max_investigation_loops == 4
    assert key.required_queries == ("checkout",)


def test_an_answer_declaring_no_optional_axis_carries_none_of_them(
    write_scenario: ScenarioWriter,
) -> None:
    key = load_scenario(write_scenario()).answer

    assert key.golden_trajectory is None
    assert key.forbidden_categories == ()
    assert key.max_investigation_loops is None


def test_a_confounder_no_recorded_response_carries_is_a_load_error(
    write_scenario: ScenarioWriter,
) -> None:
    """FR-022 is only a measurement if the agent was actually shown the confounder."""
    scenario = dict(VALID_SCENARIO)
    scenario.update(scenario_difficulty=2, adversarial_signals=["healthy_replicas_present"])

    with pytest.raises(FixtureError) as raised:
        load_scenario(write_scenario(scenario=scenario))

    assert raised.value.field == "adversarial_signals"
    assert "healthy_replicas_present" in str(raised.value)


def test_a_confounder_a_recorded_response_carries_loads(
    write_scenario: ScenarioWriter,
) -> None:
    scenario = dict(VALID_SCENARIO)
    scenario.update(scenario_difficulty=2, adversarial_signals=["healthy_replicas_present"])
    evidence = {
        "kubernetes.json": {
            "integration": "kubernetes",
            "responses": [
                {
                    "match": {"path_contains": "/events"},
                    "body": {"items": []},
                    "adversarial_signals": ["healthy_replicas_present"],
                }
            ],
        }
    }

    loaded = load_scenario(write_scenario(scenario=scenario, evidence=evidence))

    assert loaded.adversarial_signals == ("healthy_replicas_present",)
    assert loaded.evidence[0].adversarial_signals == {"healthy_replicas_present"}
