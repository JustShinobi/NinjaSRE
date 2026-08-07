"""The five demo faults, read off disk, with what each one is expected to show.

A fault is one YAML document: which flag turns it on, which service it breaks,
what symptom that produces, and what the agent is expected to conclude. Written
down before the run for the same reason a chaos experiment's expectation is —
an expected cause decided after seeing the answer is not an expectation.

Discovery walks the directory, so adding a sixth fault is adding a file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.chaos import (
    OTEL_DEMO_FAULT_IDS,
    OTEL_DEMO_FAULT_TIMEOUT_SECONDS,
    OTEL_DEMO_NAMESPACE,
)
from config.constants.evaluation import SCENARIO_DIFFICULTY_MAX, SCENARIO_DIFFICULTY_MIN
from tests.chaos.framework.catalogue import Expectation, ExperimentError, ValidityProbe
from tests.harness.schemas import read_yaml
from tests.harness.vocabularies import (
    FAILURE_MODES,
    SEVERITIES,
    evidence_sources,
    integration_names,
    root_cause_categories,
    trajectory_actions,
)

#: Where the fault declarations this repository ships live.
FAULTS_ROOT: Path = Path(__file__).resolve().parent

#: The suite a demo run is filed under, in a score and in a baseline.
DEMO_SUITE = "otel-demo"


@dataclass(frozen=True, slots=True)
class DemoFault:
    """One feature-flag fault: how to turn it on, and what it should show."""

    fault_id: str
    flag: str
    variant: str
    service: str
    expectation: Expectation
    namespace: str = OTEL_DEMO_NAMESPACE
    off_variant: str = "off"

    @property
    def key(self) -> str:
        """Return the key a score and a baseline both name this run by."""
        return f"{DEMO_SUITE}/{self.fault_id}"


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
            path,
            field_name,
            f"names {unknown}, which the controlled vocabulary does not contain",
        )


def load_fault(path: Path) -> DemoFault:
    """Return the fault declared at ``path``.

    Raises:
        ExperimentError: a field is missing or says something impossible.
    """
    document = read_yaml(path)
    if not isinstance(document, Mapping):
        raise ExperimentError(path, "document", "must be a mapping")

    probe = document.get("validity_probe")
    if not isinstance(probe, Mapping) or not str(probe.get("check", "")).strip():
        raise ExperimentError(
            path,
            "validity_probe",
            "is required: a flag that did not propagate and an agent that was wrong produce the "
            "same failed score without one",
        )

    fault_id = str(document.get("fault_id", "")).strip()
    if not fault_id:
        raise ExperimentError(path, "fault_id", "is required")
    if fault_id != path.stem:
        raise ExperimentError(path, "fault_id", f"is {fault_id!r} in a file called {path.stem!r}")

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
    equivalents = _strings(document.get("equivalent_root_cause_categories"))
    _check_in(
        (category, *forbidden, *equivalents),
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

    expectation = Expectation(
        experiment_id=fault_id,
        injected_fault=str(document.get("flag", "")),
        failure_mode=failure_mode,
        severity=severity,
        difficulty=difficulty,
        expected_symptom=_strings(document.get("expected_symptom")),
        expected_root_cause_category=category,
        required_keywords=_strings(document.get("required_keywords")),
        validity_probe=ValidityProbe(
            check=str(probe["check"]),
            namespace=str(probe.get("namespace", OTEL_DEMO_NAMESPACE)),
            timeout_seconds=float(probe.get("timeout_seconds", OTEL_DEMO_FAULT_TIMEOUT_SECONDS)),
        ),
        integrations=integrations,
        available_evidence=available,
        equivalent_root_cause_categories=equivalents,
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

    return DemoFault(
        fault_id=fault_id,
        flag=str(document.get("flag", "")),
        variant=str(document.get("variant", "on")),
        service=str(document.get("service", "")),
        expectation=expectation,
        namespace=str(document.get("namespace", OTEL_DEMO_NAMESPACE)),
        off_variant=str(document.get("off_variant", "off")),
    )


def discover_faults(root: Path = FAULTS_ROOT) -> tuple[DemoFault, ...]:
    """Return every fault declared under ``root``, in identifier order."""
    root = Path(root)
    if not root.exists():
        return ()
    return tuple(load_fault(path) for path in sorted(root.glob("*.yml")))


def declared_fault_ids() -> tuple[str, ...]:
    """Return the fault identifiers this feature promises to cover."""
    return OTEL_DEMO_FAULT_IDS


__all__ = [
    "DEMO_SUITE",
    "FAULTS_ROOT",
    "DemoFault",
    "declared_fault_ids",
    "discover_faults",
    "load_fault",
]
