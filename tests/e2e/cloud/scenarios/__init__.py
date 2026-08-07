"""The six managed-service scenarios, read off disk.

One document per scenario: which declarative module brings it up, what each of
its resources costs an hour, what fault it exercises, and what the agent is
expected to conclude. Adding a seventh is adding a file and a module — there is
no registry, for the same reason the scenario corpus has none.

The cost block is not decoration. ``bound_usd`` is what a run of this scenario
may cost and ``resources`` is what it is made of; together they are what turns
"the cloud suite is expensive" into a number somebody can compare a report
against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.chaos import CLOUD_SCENARIO_IDS
from config.constants.evaluation import SCENARIO_DIFFICULTY_MAX, SCENARIO_DIFFICULTY_MIN
from tests.chaos.framework.catalogue import Expectation, ExperimentError, ValidityProbe
from tests.e2e.cloud.cost import RatedResource, bound_for
from tests.harness.schemas import read_yaml
from tests.harness.vocabularies import (
    FAILURE_MODES,
    SEVERITIES,
    evidence_sources,
    integration_names,
    root_cause_categories,
    trajectory_actions,
)

#: Where the scenario declarations this repository ships live.
SCENARIOS_ROOT: Path = Path(__file__).resolve().parent

#: The suite a cloud run is filed under, in a score and in a baseline.
CLOUD_SUITE = "cloud"


@dataclass(frozen=True, slots=True)
class CloudScenario:
    """One managed service, provisioned, broken on purpose, and investigated."""

    scenario_id: str
    module: str
    region: str
    resources: tuple[RatedResource, ...]
    expectation: Expectation
    bound_usd: float
    variables: Mapping[str, str]
    service: str = ""

    @property
    def key(self) -> str:
        """Return the key a score and a baseline both name this run by."""
        return f"{CLOUD_SUITE}/{self.scenario_id}"

    @property
    def hourly_usd(self) -> float:
        """Return what an hour of this scenario's infrastructure costs."""
        return sum(found.hourly_total_usd for found in self.resources)


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _check_in(
    values: Sequence[str], allowed: frozenset[str], *, path: Path, field_name: str
) -> None:
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ExperimentError(
            path, field_name, f"names {unknown}, which the controlled vocabulary does not contain"
        )


def load_scenario(path: Path) -> CloudScenario:
    """Return the cloud scenario declared at ``path``.

    Raises:
        ExperimentError: a field is missing or says something impossible,
            including a scenario with no declared cost bound.
    """
    document = read_yaml(path)
    if not isinstance(document, Mapping):
        raise ExperimentError(path, "document", "must be a mapping")

    scenario_id = str(document.get("scenario_id", "")).strip()
    if scenario_id != path.stem:
        raise ExperimentError(
            path, "scenario_id", f"is {scenario_id!r} in a file called {path.stem!r}"
        )

    probe = document.get("validity_probe")
    if not isinstance(probe, Mapping) or not str(probe.get("check", "")).strip():
        raise ExperimentError(
            path,
            "validity_probe",
            "is required: infrastructure that never came up and an agent that was wrong produce "
            "the same failed score without one",
        )

    difficulty = int(document.get("difficulty", SCENARIO_DIFFICULTY_MIN))
    if not SCENARIO_DIFFICULTY_MIN <= difficulty <= SCENARIO_DIFFICULTY_MAX:
        raise ExperimentError(
            path,
            "difficulty",
            f"must be between {SCENARIO_DIFFICULTY_MIN} and {SCENARIO_DIFFICULTY_MAX}",
        )

    failure_mode = str(document.get("failure_mode", ""))
    _check_in((failure_mode,), FAILURE_MODES, path=path, field_name="failure_mode")
    severity = str(document.get("severity", "critical"))
    _check_in((severity,), SEVERITIES, path=path, field_name="severity")

    category = str(document.get("expected_root_cause_category", ""))
    forbidden = _strings(document.get("forbidden_categories"))
    _check_in(
        (category, *forbidden),
        root_cause_categories(),
        path=path,
        field_name="expected_root_cause_category",
    )

    integrations = _strings(document.get("integrations"))
    _check_in(integrations, integration_names(), path=path, field_name="integrations")
    available = _strings(document.get("available_evidence")) or integrations
    _check_in(available, evidence_sources(), path=path, field_name="available_evidence")
    trajectory = _strings(document.get("optimal_trajectory"))
    _check_in(trajectory, trajectory_actions(), path=path, field_name="optimal_trajectory")

    declared = document.get("resources")
    if not isinstance(declared, Sequence) or not declared:
        raise ExperimentError(
            path, "resources", "is required: a scenario with no priced resources has no cost bound"
        )
    resources = tuple(
        RatedResource(
            kind=str(item.get("kind", "")),
            hourly_usd=float(item.get("hourly_usd", 0.0)),
            count=int(item.get("count", 1)),
        )
        for item in declared
        if isinstance(item, Mapping)
    )

    expectation = Expectation(
        experiment_id=scenario_id,
        injected_fault=str(document.get("injected_fault", "")),
        failure_mode=failure_mode,
        severity=severity,
        difficulty=difficulty,
        expected_symptom=_strings(document.get("expected_symptom")),
        expected_root_cause_category=category,
        required_keywords=_strings(document.get("required_keywords")),
        validity_probe=ValidityProbe(
            check=str(probe["check"]),
            namespace=str(probe.get("namespace", "")),
            timeout_seconds=float(probe.get("timeout_seconds", 300.0)),
        ),
        integrations=integrations,
        available_evidence=available,
        forbidden_categories=forbidden,
        required_evidence_sources=_strings(document.get("required_evidence_sources")),
        optimal_trajectory=trajectory,
        max_investigation_loops=(
            int(document["max_investigation_loops"])
            if document.get("max_investigation_loops") is not None
            else None
        ),
        title=str(document.get("title", "")),
        team_id=str(document.get("team_id", "payments")),
    )
    if not expectation.expected_symptom or not expectation.required_keywords:
        raise ExperimentError(
            path, "expected_symptom", "and required_keywords are both required and non-empty"
        )

    return CloudScenario(
        scenario_id=scenario_id,
        module=str(document.get("module", scenario_id)),
        region=str(document.get("region", "eu-west-1")),
        resources=resources,
        expectation=expectation,
        bound_usd=float(document.get("bound_usd", bound_for(scenario_id))),
        variables={
            str(key): str(value) for key, value in (document.get("variables") or {}).items()
        },
        service=str(document.get("service", scenario_id)),
    )


def discover_scenarios(root: Path = SCENARIOS_ROOT) -> tuple[CloudScenario, ...]:
    """Return every cloud scenario under ``root``, in identifier order."""
    root = Path(root)
    if not root.exists():
        return ()
    return tuple(load_scenario(path) for path in sorted(root.glob("*.yml")))


def declared_scenario_ids() -> tuple[str, ...]:
    """Return the managed services this feature promises to cover."""
    return CLOUD_SCENARIO_IDS


__all__ = [
    "CLOUD_SUITE",
    "SCENARIOS_ROOT",
    "CloudScenario",
    "declared_scenario_ids",
    "discover_scenarios",
    "load_scenario",
]
