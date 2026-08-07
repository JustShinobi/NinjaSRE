"""Finding scenarios, resolving inheritance, and turning a directory into a value.

Discovery walks. There is no index file, and that is the property SC-005 is
made of: contributing a scenario for a new integration is creating a directory
of fixtures and an answer key, with no harness edit and no registration step.
A list would be a merge conflict on every contribution and a line somebody
eventually forgets, and a scenario that exists but was never listed fails in
the most expensive way available — by being silently absent from the number.

Inheritance exists for the family case. Four Kubernetes scenarios that differ
in one event and one answer key otherwise share a cluster, a namespace, a
workload, and an alert; writing that four times is four chances for them to
drift apart in ways nobody meant. A child names ``base:`` and states only what
differs — each key it sets replaces the base's, and each evidence file it
writes replaces the base's file of that name outright rather than merging into
it. A half-merged recorded vendor response is not a response any vendor would
ever have sent.

One imprecision worth stating: a merged manifest is validated against the
child's ``scenario.yml`` path, so a bad value inherited from a base is reported
at the child. The chain is short and the base is one directory along, which is
cheaper to live with than carrying a per-key origin map through validation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.evaluation import (
    SCENARIO_ALERT_FILENAME,
    SCENARIO_ANSWER_FILENAME,
    SCENARIO_DIFFICULTY_DESCRIPTIONS,
    SCENARIO_MANIFEST_FILENAME,
    SCENARIO_RESERVED_FILENAMES,
    SCENARIO_TRANSCRIPT_FILENAME,
)
from tests.harness.schemas import (
    DOCUMENT_FIELD,
    AlertDocument,
    FixtureError,
    read_json,
    read_yaml,
    validate_alert,
    validate_answer,
    validate_evidence,
    validate_scenario,
)

#: What a recorded response says it is when the fixture does not say.
DEFAULT_CONTENT_TYPE = "application/json"


@dataclass(frozen=True, slots=True)
class ResponseMatch:
    """Which vendor requests one recorded response answers.

    Substring matching rather than exact URLs. A client that appends a
    ``limit``, a ``timeout``, or a resource version to a query is behaving
    correctly, and a fixture pinned to the whole URL would turn every such
    change into a scenario that stopped matching and started returning the
    empty response — which reads as "the agent stopped looking".
    """

    method: str = ""
    path_contains: str = ""
    query_contains: str = ""
    body_contains: str = ""

    def matches(self, *, method: str, url: str, body: bytes | None) -> bool:
        """Return whether this matcher answers the described request."""
        if self.method and self.method.upper() != method.upper():
            return False
        if self.path_contains and self.path_contains not in url:
            return False
        if self.query_contains and self.query_contains not in url:
            return False
        if self.body_contains:
            decoded = (body or b"").decode("utf-8", errors="replace")
            if self.body_contains not in decoded:
                return False
        return True

    @property
    def specificity(self) -> int:
        """Return how narrow this matcher is, so the narrowest one wins."""
        return sum(
            len(part)
            for part in (self.method, self.path_contains, self.query_contains, self.body_contains)
        )


@dataclass(frozen=True, slots=True)
class RecordedResponse:
    """One vendor response, as it left the vendor, and what it answers."""

    match: ResponseMatch
    status: int = 200
    content_type: str = DEFAULT_CONTENT_TYPE
    body: Any | None = None
    body_text: str | None = None
    #: The planted confounders this particular response carries, so FR-022 is
    #: a fact about the evidence rather than a claim in the manifest.
    adversarial_signals: tuple[str, ...] = ()

    def payload(self) -> bytes:
        """Return the bytes a vendor would have put on the wire."""
        if self.body_text is not None:
            return self.body_text.encode("utf-8")
        return json.dumps(self.body if self.body is not None else {}).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EvidenceFixture:
    """One file of recorded responses for one integration."""

    filename: str
    integration: str
    evidence_source: str
    responses: tuple[RecordedResponse, ...]

    @property
    def adversarial_signals(self) -> frozenset[str]:
        """Return every confounder this fixture's responses say they carry."""
        return frozenset(
            signal for recorded in self.responses for signal in recorded.adversarial_signals
        )


@dataclass(frozen=True, slots=True)
class GoldenTrajectory:
    """The trajectory an ideal investigation takes, and how close still counts."""

    ordered_actions: tuple[str, ...]
    matching: str = "lcs"
    max_edit_distance: int = 0
    max_extra_actions: int = 0
    max_redundancy: int = 0


@dataclass(frozen=True, slots=True)
class AnswerKey:
    """The ground truth for one scenario, on every axis it chose to assert.

    Most fields are empty for most scenarios, and that is intended. An answer
    key asserts what its author was willing to defend; a key that filled in
    every axis by default would be asserting things nobody checked, and the
    first person to see the score move would have no way to tell which.
    """

    root_cause_category: str
    required_keywords: tuple[str, ...]
    model_response: str
    equivalent_root_cause_categories: tuple[str, ...] = ()
    forbidden_categories: tuple[str, ...] = ()
    forbidden_keywords: tuple[str, ...] = ()
    ruling_out_keywords: tuple[str, ...] = ()
    required_evidence_sources: tuple[str, ...] = ()
    required_queries: tuple[str, ...] = ()
    optimal_trajectory: tuple[str, ...] = ()
    golden_trajectory: GoldenTrajectory | None = None
    max_investigation_loops: int | None = None

    @property
    def accepted_categories(self) -> frozenset[str]:
        """Return every category that counts as correct for this scenario."""
        return frozenset((self.root_cause_category, *self.equivalent_root_cause_categories))


@dataclass(frozen=True, slots=True)
class Scenario:
    """One incident: what it is, what can be seen of it, and what the answer is."""

    directory: Path
    suite: str
    scenario_id: str
    failure_mode: str
    severity: str
    difficulty: int
    adversarial_signals: tuple[str, ...]
    available_evidence: tuple[str, ...]
    integrations: tuple[str, ...]
    alert: AlertDocument
    answer: AnswerKey
    evidence: tuple[EvidenceFixture, ...]
    team_id: str = "payments"
    title: str = ""
    transcript_path: Path | None = None

    @property
    def key(self) -> str:
        """Return the identifier a filter and a report both use."""
        return f"{self.suite}/{self.scenario_id}"

    @property
    def difficulty_description(self) -> str:
        """Return the one sentence defining this scenario's level."""
        return SCENARIO_DIFFICULTY_DESCRIPTIONS.get(self.difficulty, "")

    @property
    def offline_ready(self) -> bool:
        """Return whether this scenario can run with no provider at all."""
        return self.transcript_path is not None and self.transcript_path.exists()


class ScenarioNotFound(Exception):
    """A directory was asked to be a scenario and holds no manifest."""


def _raw_manifest(directory: Path) -> Mapping[str, Any]:
    """Return the unvalidated manifest in ``directory``, or raise naming the file."""
    manifest = directory / SCENARIO_MANIFEST_FILENAME
    document = read_yaml(manifest)
    if not isinstance(document, Mapping):
        raise FixtureError(
            manifest, DOCUMENT_FIELD, f"must be a mapping, got {type(document).__name__}"
        )
    return document


def _inheritance_chain(directory: Path) -> tuple[Path, ...]:
    """Return the scenario directories to merge, base-most first.

    Raises:
        FixtureError: a ``base`` names nothing, or the chain loops.
    """
    chain: list[Path] = []
    visited: set[Path] = set()
    current = directory.resolve()

    while True:
        manifest = current / SCENARIO_MANIFEST_FILENAME
        document = _raw_manifest(current)
        chain.append(current)
        visited.add(current)

        declared = document.get("base")
        if declared is None:
            break
        if not isinstance(declared, str) or not declared.strip():
            raise FixtureError(manifest, "base", "must be a non-empty scenario directory name")

        parent = (current.parent / declared.strip()).resolve()
        if parent == current or parent in visited:
            raise FixtureError(
                manifest,
                "base",
                f"names {declared.strip()!r}, which is already in this scenario's inheritance "
                f"chain; a scenario cannot be its own base",
            )
        if not (parent / SCENARIO_MANIFEST_FILENAME).exists():
            raise FixtureError(
                manifest,
                "base",
                f"names {declared.strip()!r}, and there is no scenario directory of that name "
                f"beside this one in {current.parent}",
            )
        current = parent

    return tuple(reversed(chain))


def _evidence_files(directory: Path) -> dict[str, Path]:
    """Return the evidence fixtures in ``directory``, keyed by filename."""
    return {
        found.name: found
        for found in sorted(directory.glob("*.json"))
        if found.name not in SCENARIO_RESERVED_FILENAMES
    }


def _answer_key(document: Mapping[str, Any]) -> AnswerKey:
    """Return the validated answer document as a value."""
    golden = document.get("golden_trajectory")
    return AnswerKey(
        root_cause_category=document["root_cause_category"],
        required_keywords=tuple(document["required_keywords"]),
        model_response=document["model_response"],
        equivalent_root_cause_categories=tuple(
            document.get("equivalent_root_cause_categories", ())
        ),
        forbidden_categories=tuple(document.get("forbidden_categories", ())),
        forbidden_keywords=tuple(document.get("forbidden_keywords", ())),
        ruling_out_keywords=tuple(document.get("ruling_out_keywords", ())),
        required_evidence_sources=tuple(document.get("required_evidence_sources", ())),
        required_queries=tuple(document.get("required_queries", ())),
        optimal_trajectory=tuple(document.get("optimal_trajectory", ())),
        golden_trajectory=(
            GoldenTrajectory(
                ordered_actions=tuple(golden["ordered_actions"]),
                matching=golden.get("matching", "lcs"),
                max_edit_distance=golden.get("max_edit_distance", 0),
                max_extra_actions=golden.get("max_extra_actions", 0),
                max_redundancy=golden.get("max_redundancy", 0),
            )
            if isinstance(golden, Mapping)
            else None
        ),
        max_investigation_loops=document.get("max_investigation_loops"),
    )


def _evidence_fixture(path: Path) -> EvidenceFixture:
    """Return the validated evidence fixture at ``path`` as a value."""
    document = validate_evidence(read_json(path), path=path)
    integration = document["integration"]
    return EvidenceFixture(
        filename=path.name,
        integration=integration,
        evidence_source=document.get("evidence_source", integration),
        responses=tuple(
            RecordedResponse(
                match=ResponseMatch(**dict(entry.get("match", {}))),
                status=entry.get("status", 200),
                content_type=entry.get("content_type", DEFAULT_CONTENT_TYPE),
                body=entry.get("body"),
                body_text=entry.get("body_text"),
                adversarial_signals=tuple(entry.get("adversarial_signals", ())),
            )
            for entry in document["responses"]
        ),
    )


def _check_confounders_are_visible(
    declared: Sequence[str], evidence: Sequence[EvidenceFixture], *, path: Path
) -> None:
    """Raise unless every declared confounder is carried by some recorded response.

    FR-022 says adversarial signals are declared per scenario so resistance can
    be reported separately from accuracy. That is only a measurement if the
    confounder is in the evidence the agent can see — a scenario naming one that
    appears nowhere would report resistance to something nobody was shown, which
    is the most flattering kind of wrong number a suite can produce.
    """
    carried = {signal for fixture in evidence for signal in fixture.adversarial_signals}
    absent = [signal for signal in declared if signal not in carried]
    if absent:
        raise FixtureError(
            path,
            "adversarial_signals",
            f"declares {absent} which no recorded response says it carries; mark the "
            f"response that plants each confounder with its own 'adversarial_signals' so "
            f"the suite is reporting resistance to evidence the agent actually saw",
        )


def load_scenario(directory: Path, *, root: Path | None = None) -> Scenario:
    """Return the scenario in ``directory``, inheritance resolved.

    ``root`` names the corpus root, and is what gives a scenario its suite: the
    path from the root down to the scenario's own directory. Without one the
    parent directory's name is used, which is what a single-directory load
    means anyway.

    Raises:
        FixtureError: any fixture is missing or malformed, naming file and field.
    """
    directory = Path(directory)
    chain = _inheritance_chain(directory)

    manifest_document: dict[str, Any] = {}
    alert_path: Path | None = None
    answer_path: Path | None = None
    transcript_path: Path | None = None
    evidence_paths: dict[str, Path] = {}

    for ancestor in chain:
        manifest_document.update(_raw_manifest(ancestor))
        if (ancestor / SCENARIO_ALERT_FILENAME).exists():
            alert_path = ancestor / SCENARIO_ALERT_FILENAME
        if (ancestor / SCENARIO_ANSWER_FILENAME).exists():
            answer_path = ancestor / SCENARIO_ANSWER_FILENAME
        if (ancestor / SCENARIO_TRANSCRIPT_FILENAME).exists():
            transcript_path = ancestor / SCENARIO_TRANSCRIPT_FILENAME
        evidence_paths.update(_evidence_files(ancestor))

    manifest_path = directory / SCENARIO_MANIFEST_FILENAME
    manifest = validate_scenario(manifest_document, path=manifest_path)

    alert = validate_alert(
        read_json(alert_path if alert_path is not None else directory / SCENARIO_ALERT_FILENAME),
        path=alert_path if alert_path is not None else directory / SCENARIO_ALERT_FILENAME,
    )
    answer_at = answer_path if answer_path is not None else directory / SCENARIO_ANSWER_FILENAME
    answer = _answer_key(
        validate_answer(
            read_yaml(answer_at),
            path=answer_at,
            available_evidence=manifest["available_evidence"],
        )
    )

    evidence = tuple(_evidence_fixture(path) for _, path in sorted(evidence_paths.items()))
    _check_confounders_are_visible(manifest["adversarial_signals"], evidence, path=manifest_path)

    if root is not None:
        parts = directory.resolve().relative_to(Path(root).resolve()).parts[:-1]
        suite = "/".join(parts) if parts else directory.parent.name
    else:
        suite = directory.parent.name

    return Scenario(
        directory=directory,
        suite=suite,
        scenario_id=manifest["scenario_id"],
        failure_mode=manifest["failure_mode"],
        severity=manifest["severity"],
        difficulty=manifest["scenario_difficulty"],
        adversarial_signals=tuple(manifest["adversarial_signals"]),
        available_evidence=tuple(manifest["available_evidence"]),
        integrations=tuple(manifest["integrations"]),
        alert=alert,
        answer=answer,
        evidence=evidence,
        team_id=manifest.get("team_id", "payments"),
        title=manifest.get("title", ""),
        transcript_path=transcript_path,
    )


def discover_scenarios(root: Path) -> tuple[Scenario, ...]:
    """Return every scenario under ``root``, ordered by suite then identifier.

    Walking rather than reading an index is what makes contributing a scenario
    a matter of adding a directory (SC-005). A directory holding no manifest is
    not a scenario and is passed over in silence — notes, tooling, and
    ``__pycache__`` all live perfectly well beside a corpus.
    """
    root = Path(root)
    if not root.exists():
        return ()
    directories = sorted({found.parent for found in root.rglob(SCENARIO_MANIFEST_FILENAME)})
    scenarios = [load_scenario(directory, root=root) for directory in directories]
    return tuple(sorted(scenarios, key=lambda found: (found.suite, found.scenario_id)))


def filter_scenarios(
    scenarios: Sequence[Scenario],
    *,
    suite: str = "",
    scenario_id: str = "",
    difficulty: int | None = None,
    integration: str = "",
    offline_only: bool = False,
) -> tuple[Scenario, ...]:
    """Return the scenarios matching every filter that was given.

    Substring matching on suite and identifier, because the thing a contributor
    types is ``liveness`` and not ``kubernetes/004-liveness-probe-killing``.
    """
    selected = list(scenarios)
    if suite:
        selected = [found for found in selected if suite in found.suite]
    if scenario_id:
        selected = [found for found in selected if scenario_id in found.scenario_id]
    if difficulty is not None:
        selected = [found for found in selected if found.difficulty == difficulty]
    if integration:
        selected = [found for found in selected if integration in found.integrations]
    if offline_only:
        selected = [found for found in selected if found.offline_ready]
    return tuple(selected)


__all__ = [
    "DEFAULT_CONTENT_TYPE",
    "AnswerKey",
    "EvidenceFixture",
    "GoldenTrajectory",
    "RecordedResponse",
    "ResponseMatch",
    "Scenario",
    "ScenarioNotFound",
    "discover_scenarios",
    "filter_scenarios",
    "load_scenario",
]
