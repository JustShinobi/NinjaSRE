"""Reading an experiment off disk, and refusing one that has not said enough.

An experiment is three files in a directory, and the loader is strict about all
three for the same reason the scenario loader is strict about its fixtures: a
malformed experiment discovered during a chaos run has already cost a cluster, an
injection, and an investigation before anybody sees the problem.

The strictness that matters most is ``expected.yml``. The expected symptom and
the expected cause have to be written down *before* the run, and this is where
that becomes mechanical rather than cultural: an experiment with no
declared symptom cannot be loaded, so it cannot be run, so there is no path by
which somebody decides after the fact what the run was supposed to show.

Discovery walks. There is no index, so contributing an experiment is adding a
directory — the same property that makes the scenario corpus contributable, for
the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.chaos import (
    CHAOS_ALERT_FILENAME,
    CHAOS_EXPECTATION_FILENAME,
    CHAOS_MANIFEST_FILENAME,
    CHAOS_VALIDITY_TIMEOUT_SECONDS,
)
from config.constants.evaluation import SCENARIO_DIFFICULTY_MAX, SCENARIO_DIFFICULTY_MIN
from tests.harness.schemas import read_json, read_yaml
from tests.harness.vocabularies import (
    FAILURE_MODES,
    SEVERITIES,
    evidence_sources,
    integration_names,
    root_cause_categories,
    trajectory_actions,
)

#: Where the experiments this repository ships live.
EXPERIMENTS_ROOT: Path = Path(__file__).resolve().parents[1] / "experiments"


class ExperimentError(Exception):
    """An experiment directory is missing something, or says something impossible.

    Names the file and the field, because the person reading this is editing one
    of three small documents and "invalid experiment" would send them to all of
    them.
    """

    def __init__(self, path: Path, field_name: str, problem: str) -> None:
        self.path = path
        self.field_name = field_name
        super().__init__(f"{path}: {field_name} {problem}")


@dataclass(frozen=True, slots=True)
class ValidityProbe:
    """How this experiment confirms the fault actually took effect.

    Without one, a flaky injection is indistinguishable from an agent
    regression — the run scores badly either way — and a suite whose failures
    cannot be attributed is one nobody acts on.
    """

    check: str
    namespace: str = ""
    timeout_seconds: float = CHAOS_VALIDITY_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class Expectation:
    """What one experiment says it will produce, declared before it runs."""

    experiment_id: str
    injected_fault: str
    failure_mode: str
    severity: str
    difficulty: int
    expected_symptom: tuple[str, ...]
    expected_root_cause_category: str
    required_keywords: tuple[str, ...]
    validity_probe: ValidityProbe
    integrations: tuple[str, ...] = ()
    available_evidence: tuple[str, ...] = ()
    equivalent_root_cause_categories: tuple[str, ...] = ()
    forbidden_categories: tuple[str, ...] = ()
    required_evidence_sources: tuple[str, ...] = ()
    optimal_trajectory: tuple[str, ...] = ()
    max_investigation_loops: int | None = None
    title: str = ""
    team_id: str = "payments"


@dataclass(frozen=True, slots=True)
class Experiment:
    """One declarative fault, its alert, and what it is expected to show."""

    directory: Path
    manifest: Mapping[str, Any]
    alert: Mapping[str, Any]
    expectation: Expectation

    @property
    def experiment_id(self) -> str:
        """Return the identifier this experiment is reported under."""
        return self.expectation.experiment_id

    @property
    def key(self) -> str:
        """Return the key a score and a baseline both name this run by."""
        return f"chaos/{self.experiment_id}"


def _required(document: Mapping[str, Any], name: str, *, path: Path) -> Any:
    """Return ``name`` from ``document`` or raise naming the file and the field."""
    value = document.get(name)
    if value is None or (isinstance(value, str | list | tuple) and not value):
        raise ExperimentError(path, name, "is required and must not be empty")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    """Return ``value`` as a tuple of strings, whatever shape YAML produced."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _check_in(
    values: Sequence[str], allowed: frozenset[str], *, path: Path, field_name: str
) -> None:
    """Raise unless every value is in the controlled vocabulary ``allowed``."""
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ExperimentError(
            path,
            field_name,
            f"names {unknown}, which the controlled vocabulary does not contain; a name that "
            f"nothing in the running system answers to would be scored against forever without "
            f"ever matching",
        )


def _expectation(document: Mapping[str, Any], *, path: Path) -> Expectation:
    """Return the validated expectation document as a value."""
    probe = document.get("validity_probe")
    if not isinstance(probe, Mapping) or not str(probe.get("check", "")).strip():
        raise ExperimentError(
            path,
            "validity_probe",
            "is required and must name a check; without one a flaky injection is reported as an "
            "agent regression",
        )

    difficulty = int(document.get("difficulty", SCENARIO_DIFFICULTY_MIN))
    if not SCENARIO_DIFFICULTY_MIN <= difficulty <= SCENARIO_DIFFICULTY_MAX:
        raise ExperimentError(
            path,
            "difficulty",
            f"must be between {SCENARIO_DIFFICULTY_MIN} and {SCENARIO_DIFFICULTY_MAX}",
        )

    failure_mode = str(_required(document, "failure_mode", path=path))
    _check_in((failure_mode,), FAILURE_MODES, path=path, field_name="failure_mode")

    severity = str(_required(document, "severity", path=path))
    _check_in((severity,), SEVERITIES, path=path, field_name="severity")

    category = str(_required(document, "expected_root_cause_category", path=path))
    equivalents = _strings(document.get("equivalent_root_cause_categories"))
    forbidden = _strings(document.get("forbidden_categories"))
    _check_in(
        (category, *equivalents, *forbidden),
        root_cause_categories(),
        path=path,
        field_name="expected_root_cause_category",
    )

    integrations = _strings(_required(document, "integrations", path=path))
    _check_in(integrations, integration_names(), path=path, field_name="integrations")

    available = _strings(document.get("available_evidence")) or integrations
    _check_in(available, evidence_sources(), path=path, field_name="available_evidence")

    required_sources = _strings(document.get("required_evidence_sources"))
    absent = [source for source in required_sources if source not in available]
    if absent:
        raise ExperimentError(
            path,
            "required_evidence_sources",
            f"names {absent}, which the experiment does not list as available; an answer key "
            f"cannot require evidence from a source the run cannot reach",
        )

    trajectory = _strings(document.get("optimal_trajectory"))
    _check_in(trajectory, trajectory_actions(), path=path, field_name="optimal_trajectory")

    return Expectation(
        experiment_id=str(_required(document, "experiment_id", path=path)),
        injected_fault=str(_required(document, "injected_fault", path=path)),
        failure_mode=failure_mode,
        severity=severity,
        difficulty=difficulty,
        expected_symptom=_strings(_required(document, "expected_symptom", path=path)),
        expected_root_cause_category=category,
        required_keywords=_strings(_required(document, "required_keywords", path=path)),
        validity_probe=ValidityProbe(
            check=str(probe["check"]),
            namespace=str(probe.get("namespace", "")),
            timeout_seconds=float(probe.get("timeout_seconds", CHAOS_VALIDITY_TIMEOUT_SECONDS)),
        ),
        integrations=integrations,
        available_evidence=available,
        equivalent_root_cause_categories=equivalents,
        forbidden_categories=forbidden,
        required_evidence_sources=required_sources,
        optimal_trajectory=trajectory,
        max_investigation_loops=(
            int(document["max_investigation_loops"])
            if document.get("max_investigation_loops") is not None
            else None
        ),
        title=str(document.get("title", "")),
        team_id=str(document.get("team_id", "payments")),
    )


def load_experiment(directory: Path) -> Experiment:
    """Return the experiment in ``directory``.

    Raises:
        ExperimentError: a file is missing or a field says something impossible.
    """
    directory = Path(directory)
    manifest_path = directory / CHAOS_MANIFEST_FILENAME
    alert_path = directory / CHAOS_ALERT_FILENAME
    expected_path = directory / CHAOS_EXPECTATION_FILENAME

    for path in (manifest_path, alert_path, expected_path):
        if not path.exists():
            raise ExperimentError(path, "file", "is missing from this experiment directory")

    manifest = read_yaml(manifest_path)
    if not isinstance(manifest, Mapping):
        raise ExperimentError(manifest_path, "document", "must be a mapping")

    alert = read_json(alert_path)
    if not isinstance(alert, Mapping):
        raise ExperimentError(alert_path, "document", "must be a mapping")

    document = read_yaml(expected_path)
    if not isinstance(document, Mapping):
        raise ExperimentError(expected_path, "document", "must be a mapping")

    expectation = _expectation(document, path=expected_path)
    if expectation.experiment_id != directory.name:
        raise ExperimentError(
            expected_path,
            "experiment_id",
            f"is {expectation.experiment_id!r} in a directory called {directory.name!r}; the two "
            f"are one identifier and a report reads whichever it was handed",
        )

    return Experiment(
        directory=directory, manifest=dict(manifest), alert=dict(alert), expectation=expectation
    )


def discover_experiments(root: Path = EXPERIMENTS_ROOT) -> tuple[Experiment, ...]:
    """Return every experiment under ``root``, in identifier order."""
    root = Path(root)
    if not root.exists():
        return ()
    directories = sorted({found.parent for found in root.rglob(CHAOS_MANIFEST_FILENAME)})
    return tuple(load_experiment(directory) for directory in directories)


@dataclass(frozen=True, slots=True)
class ExperimentFilter:
    """Which experiments a run covers, so a contributor can run one of fourteen."""

    experiment_id: str = ""
    failure_modes: tuple[str, ...] = field(default_factory=tuple)

    def select(self, experiments: Sequence[Experiment]) -> tuple[Experiment, ...]:
        """Return the experiments matching every filter that was given."""
        selected = list(experiments)
        if self.experiment_id:
            selected = [found for found in selected if self.experiment_id in found.experiment_id]
        if self.failure_modes:
            selected = [
                found for found in selected if found.expectation.failure_mode in self.failure_modes
            ]
        return tuple(selected)


__all__ = [
    "EXPERIMENTS_ROOT",
    "Expectation",
    "Experiment",
    "ExperimentError",
    "ExperimentFilter",
    "ValidityProbe",
    "discover_experiments",
    "load_experiment",
]
