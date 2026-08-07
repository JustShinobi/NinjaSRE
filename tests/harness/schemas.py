"""What a scenario's four fixture kinds are, and what makes one malformed.

The typed documents below are the contract; the validators are what makes it
enforceable. Both matter, and the second is the one that pays for itself: a
``KeyError: 'severity'`` in the middle of a suite run tells the author that
something is missing without telling them which of forty scenarios is missing
it, and the fixture format is only a format if a mistake in it is caught where
the mistake is.

So every failure raised here carries the file and the field, and the message
says both. That is the whole of SC-003.

Validation is strict about vocabulary and lenient about nothing else. A typo in
a failure mode, an evidence source, a root-cause category, or a trajectory
action is a load error, because each of those is compared for equality later
and a near-miss scores as a miss with no indication that a human meant
otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from config.constants.evaluation import (
    SCENARIO_ADVERSARIAL_FROM_DIFFICULTY,
    SCENARIO_DIFFICULTY_MAX,
    SCENARIO_DIFFICULTY_MIN,
    SCENARIO_SCHEMA_VERSION,
)
from config.constants.investigation import MAX_INVESTIGATION_LOOPS
from tests.harness.vocabularies import (
    ADVERSARIAL_SIGNALS,
    FAILURE_MODES,
    SEVERITIES,
    TRAJECTORY_MATCHINGS,
    evidence_sources,
    integration_names,
    root_cause_categories,
    trajectory_actions,
)

#: The field name reported when the problem is with the document as a whole —
#: it is missing, it is unreadable, or it is not a mapping at all.
DOCUMENT_FIELD = "<document>"


class FixtureError(Exception):
    """A fixture could not be loaded, and this says which file and which field.

    ``path`` and ``field`` are attributes rather than only being interpolated
    into the message, because a suite that collects load failures wants to
    group them by file, and re-parsing its own error strings to do that is how
    a harness acquires a private grammar nobody documented.
    """

    def __init__(self, path: Path, field: str, problem: str) -> None:
        self.path = path
        self.field = field
        self.problem = problem
        super().__init__(f"{path}: {field}: {problem}")


# --- Typed documents ---------------------------------------------------------


class ScenarioDocument(TypedDict):
    """``scenario.yml`` — what this incident is, and what can be seen of it."""

    schema_version: str
    scenario_id: str
    failure_mode: str
    severity: str
    scenario_difficulty: int
    available_evidence: list[str]
    integrations: list[str]
    adversarial_signals: list[str]
    base: NotRequired[str]
    team_id: NotRequired[str]
    title: NotRequired[str]


class AlertDocument(TypedDict):
    """``alert.json`` — the trigger, in whatever shape its source really sends."""

    payload: NotRequired[dict[str, Any]]
    text: NotRequired[str]
    source_hint: NotRequired[str]
    received_at: NotRequired[str]


class ResponseMatchDocument(TypedDict):
    """Which vendor requests one recorded response answers."""

    method: NotRequired[str]
    path_contains: NotRequired[str]
    query_contains: NotRequired[str]
    body_contains: NotRequired[str]


class RecordedResponseDocument(TypedDict):
    """One recorded vendor response, as it left the vendor.

    ``adversarial_signals`` is how a fixture says which planted confounder *this
    response* carries. Declaring them only on the scenario would make FR-022 a
    claim rather than a fact: a scenario could name a confounder that appears
    nowhere in the evidence, and the suite would report resistance to something
    the agent was never shown.
    """

    match: NotRequired[ResponseMatchDocument]
    status: NotRequired[int]
    content_type: NotRequired[str]
    body: NotRequired[Any]
    body_text: NotRequired[str]
    adversarial_signals: NotRequired[list[str]]


class EvidenceDocument(TypedDict):
    """One evidence fixture: an integration, and what its vendor answers."""

    integration: str
    responses: list[RecordedResponseDocument]
    evidence_source: NotRequired[str]


class GoldenTrajectoryDocument(TypedDict):
    """The trajectory an ideal investigation takes, and how close counts."""

    ordered_actions: list[str]
    matching: NotRequired[str]
    max_edit_distance: NotRequired[int]
    max_extra_actions: NotRequired[int]
    max_redundancy: NotRequired[int]


class AnswerDocument(TypedDict):
    """``answer.yml`` — the ground truth, on every axis it chooses to assert."""

    root_cause_category: str
    required_keywords: list[str]
    model_response: str
    equivalent_root_cause_categories: NotRequired[list[str]]
    forbidden_categories: NotRequired[list[str]]
    forbidden_keywords: NotRequired[list[str]]
    ruling_out_keywords: NotRequired[list[str]]
    required_evidence_sources: NotRequired[list[str]]
    required_queries: NotRequired[list[str]]
    optimal_trajectory: NotRequired[list[str]]
    golden_trajectory: NotRequired[GoldenTrajectoryDocument]
    max_investigation_loops: NotRequired[int]


# --- Reading helpers ---------------------------------------------------------


def read_json(path: Path) -> Any:
    """Return the JSON document at ``path``.

    Raises:
        FixtureError: the file is missing or is not valid JSON.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureError(path, DOCUMENT_FIELD, f"could not be read: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise FixtureError(path, DOCUMENT_FIELD, f"is not valid JSON: {error}") from error


def read_yaml(path: Path) -> Any:
    """Return the YAML document at ``path``.

    Raises:
        FixtureError: the file is missing or is not valid YAML.
    """
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureError(path, DOCUMENT_FIELD, f"could not be read: {error}") from error
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise FixtureError(path, DOCUMENT_FIELD, f"is not valid YAML: {error}") from error


def _mapping(value: Any, *, path: Path, field: str) -> Mapping[str, Any]:
    """Return ``value`` as a mapping, or raise naming ``field``."""
    if not isinstance(value, Mapping):
        raise FixtureError(path, field, f"must be a mapping, got {type(value).__name__}")
    return value


def _text(document: Mapping[str, Any], key: str, *, path: Path, field: str = "") -> str:
    """Return the non-empty string at ``key``, or raise naming it."""
    name = field or key
    if key not in document:
        raise FixtureError(path, name, "is required and is missing")
    value = document[key]
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(path, name, "must be a non-empty string")
    return value.strip()


def _integer(document: Mapping[str, Any], key: str, *, path: Path, field: str = "") -> int:
    """Return the integer at ``key``, or raise naming it."""
    name = field or key
    if key not in document:
        raise FixtureError(path, name, "is required and is missing")
    value = document[key]
    # ``bool`` is an ``int`` in Python, and a difficulty of ``True`` is a typo.
    if isinstance(value, bool) or not isinstance(value, int):
        raise FixtureError(path, name, f"must be an integer, got {value!r}")
    return value


def _strings(
    document: Mapping[str, Any],
    key: str,
    *,
    path: Path,
    field: str = "",
    required: bool = False,
) -> tuple[str, ...]:
    """Return the list of strings at ``key``, or raise naming it."""
    name = field or key
    if key not in document:
        if required:
            raise FixtureError(path, name, "is required and is missing")
        return ()
    value = document[key]
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise FixtureError(path, name, f"must be a list of strings, got {type(value).__name__}")
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise FixtureError(path, name, f"must contain non-empty strings, got {entry!r}")
    return tuple(entry.strip() for entry in value)


def _within(
    values: Sequence[str],
    vocabulary: frozenset[str] | set[str],
    *,
    path: Path,
    field: str,
    subject: str,
) -> tuple[str, ...]:
    """Return ``values``, or raise naming the first one outside ``vocabulary``."""
    for value in values:
        if value not in vocabulary:
            near = sorted(term for term in vocabulary if term.startswith(value[:4]))[:3]
            hint = f"; did you mean {near}?" if near else ""
            raise FixtureError(path, field, f"{value!r} is not {subject}{hint}")
    return tuple(values)


# --- Validators --------------------------------------------------------------


def validate_scenario(document: Any, *, path: Path) -> ScenarioDocument:
    """Return ``document`` as a validated scenario manifest.

    Raises:
        FixtureError: naming the file and the first field that is wrong.
    """
    values = _mapping(document, path=path, field=DOCUMENT_FIELD)

    version = _text(values, "schema_version", path=path)
    if version != SCENARIO_SCHEMA_VERSION:
        raise FixtureError(
            path,
            "schema_version",
            f"is {version!r}; this loader reads {SCENARIO_SCHEMA_VERSION!r} and refuses to "
            f"guess at another",
        )

    difficulty = _integer(values, "scenario_difficulty", path=path)
    if not SCENARIO_DIFFICULTY_MIN <= difficulty <= SCENARIO_DIFFICULTY_MAX:
        raise FixtureError(
            path,
            "scenario_difficulty",
            f"must be between {SCENARIO_DIFFICULTY_MIN} and {SCENARIO_DIFFICULTY_MAX}, "
            f"got {difficulty}",
        )

    signals = _within(
        _strings(values, "adversarial_signals", path=path),
        ADVERSARIAL_SIGNALS,
        path=path,
        field="adversarial_signals",
        subject="a declared adversarial signal",
    )
    if difficulty >= SCENARIO_ADVERSARIAL_FROM_DIFFICULTY and not signals:
        raise FixtureError(
            path,
            "adversarial_signals",
            f"difficulty {difficulty} means at least one planted confounder, and none is "
            f"declared; a scenario whose confounders are undeclared cannot be reported on "
            f"separately from plain accuracy",
        )

    available = _within(
        _strings(values, "available_evidence", path=path, required=True),
        evidence_sources(),
        path=path,
        field="available_evidence",
        subject="an evidence source anything in this repository provides",
    )
    if not available:
        raise FixtureError(path, "available_evidence", "must name at least one evidence source")

    declared = _strings(values, "integrations", path=path)
    integrations = declared or tuple(
        source for source in available if source in integration_names()
    )
    _within(
        integrations,
        integration_names(),
        path=path,
        field="integrations",
        subject="an integration this repository ships",
    )

    validated: ScenarioDocument = {
        "schema_version": version,
        "scenario_id": _text(values, "scenario_id", path=path),
        "failure_mode": _within(
            (_text(values, "failure_mode", path=path),),
            FAILURE_MODES,
            path=path,
            field="failure_mode",
            subject="a declared failure mode",
        )[0],
        "severity": _within(
            (_text(values, "severity", path=path),),
            SEVERITIES,
            path=path,
            field="severity",
            subject="a severity the alert adapters normalise onto",
        )[0],
        "scenario_difficulty": difficulty,
        "available_evidence": list(available),
        "integrations": list(integrations),
        "adversarial_signals": list(signals),
    }
    if "base" in values:
        validated["base"] = _text(values, "base", path=path)
    if "team_id" in values:
        validated["team_id"] = _text(values, "team_id", path=path)
    if "title" in values:
        validated["title"] = _text(values, "title", path=path)
    return validated


def validate_alert(document: Any, *, path: Path) -> AlertDocument:
    """Return ``document`` as a validated alert trigger.

    Raises:
        FixtureError: naming the file and the first field that is wrong.
    """
    values = _mapping(document, path=path, field=DOCUMENT_FIELD)

    validated: AlertDocument = {}
    if "payload" in values:
        payload = values["payload"]
        if not isinstance(payload, Mapping):
            raise FixtureError(path, "payload", f"must be a mapping, got {type(payload).__name__}")
        validated["payload"] = dict(payload)
    if "text" in values:
        text = values["text"]
        if not isinstance(text, str):
            raise FixtureError(path, "text", f"must be a string, got {type(text).__name__}")
        validated["text"] = text

    if not validated.get("payload") and not validated.get("text", "").strip():
        raise FixtureError(
            path,
            "payload",
            "an alert must carry either a vendor 'payload' or free 'text'; this one carries "
            "neither, so there is nothing for intake to read",
        )

    for optional in ("source_hint", "received_at"):
        if optional in values:
            validated[optional] = _text(values, optional, path=path)  # type: ignore[literal-required]
    return validated


def validate_evidence(document: Any, *, path: Path) -> EvidenceDocument:
    """Return ``document`` as a validated evidence fixture.

    Raises:
        FixtureError: naming the file and the first field that is wrong.
    """
    values = _mapping(document, path=path, field=DOCUMENT_FIELD)

    integration = _within(
        (_text(values, "integration", path=path),),
        integration_names(),
        path=path,
        field="integration",
        subject="an integration this repository ships",
    )[0]

    if "responses" not in values:
        raise FixtureError(
            path,
            "responses",
            "is required: an evidence fixture with no recorded responses serves nothing, and "
            "an empty file is indistinguishable from one nobody finished",
        )
    raw = values["responses"]
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise FixtureError(path, "responses", f"must be a list, got {type(raw).__name__}")
    if not raw:
        raise FixtureError(path, "responses", "must contain at least one recorded response")

    responses: list[RecordedResponseDocument] = []
    for index, entry in enumerate(raw):
        responses.append(_validate_response(entry, path=path, field=f"responses[{index}]"))

    validated: EvidenceDocument = {"integration": integration, "responses": responses}
    if "evidence_source" in values:
        validated["evidence_source"] = _within(
            (_text(values, "evidence_source", path=path),),
            evidence_sources(),
            path=path,
            field="evidence_source",
            subject="an evidence source anything in this repository provides",
        )[0]
    return validated


def _validate_response(entry: Any, *, path: Path, field: str) -> RecordedResponseDocument:
    """Return one recorded response, validated, or raise naming its field."""
    values = _mapping(entry, path=path, field=field)

    validated: RecordedResponseDocument = {}
    if "match" in values:
        match = _mapping(values["match"], path=path, field=f"{field}.match")
        allowed = {"method", "path_contains", "query_contains", "body_contains"}
        unknown = sorted(set(match) - allowed)
        if unknown:
            raise FixtureError(
                path,
                f"{field}.match",
                f"has no matcher called {unknown[0]!r}; allowed: {sorted(allowed)}",
            )
        validated["match"] = {  # type: ignore[typeddict-item]
            key: _text(match, key, path=path, field=f"{field}.match.{key}") for key in match
        }

    if "status" in values:
        validated["status"] = _integer(values, "status", path=path, field=f"{field}.status")
    if "content_type" in values:
        validated["content_type"] = _text(
            values, "content_type", path=path, field=f"{field}.content_type"
        )

    if "adversarial_signals" in values:
        validated["adversarial_signals"] = list(
            _within(
                _strings(
                    values,
                    "adversarial_signals",
                    path=path,
                    field=f"{field}.adversarial_signals",
                ),
                ADVERSARIAL_SIGNALS,
                path=path,
                field=f"{field}.adversarial_signals",
                subject="a declared adversarial signal",
            )
        )

    if "body_text" in values:
        body_text = values["body_text"]
        if not isinstance(body_text, str):
            raise FixtureError(path, f"{field}.body_text", "must be a string")
        validated["body_text"] = body_text
    elif "body" in values:
        validated["body"] = values["body"]
    else:
        raise FixtureError(
            path,
            f"{field}.body",
            "a recorded response must carry a 'body' (JSON) or a 'body_text' (anything else)",
        )
    return validated


def validate_answer(
    document: Any, *, path: Path, available_evidence: Sequence[str] = ()
) -> AnswerDocument:
    """Return ``document`` as a validated answer key.

    ``available_evidence`` is the scenario's own declaration. An answer key that
    demands evidence the scenario cannot serve is unsatisfiable by construction,
    and a scenario nothing can pass is worse than no scenario: it looks like a
    finding.

    Raises:
        FixtureError: naming the file and the first field that is wrong.
    """
    values = _mapping(document, path=path, field=DOCUMENT_FIELD)
    categories = root_cause_categories()
    actions = trajectory_actions()

    validated: AnswerDocument = {
        "root_cause_category": _within(
            (_text(values, "root_cause_category", path=path),),
            categories,
            path=path,
            field="root_cause_category",
            subject="a category in the shipped taxonomy",
        )[0],
        "required_keywords": list(_strings(values, "required_keywords", path=path, required=True)),
        "model_response": _text(values, "model_response", path=path),
    }
    if not validated["required_keywords"]:
        raise FixtureError(
            path,
            "required_keywords",
            "must name at least one keyword: an answer key with none asserts nothing about "
            "what the diagnosis said",
        )

    for field, vocabulary, subject in (
        ("equivalent_root_cause_categories", categories, "a category in the shipped taxonomy"),
        ("forbidden_categories", categories, "a category in the shipped taxonomy"),
        ("optimal_trajectory", actions, "a capability this repository declares"),
    ):
        if field in values:
            validated[field] = list(  # type: ignore[literal-required]
                _within(
                    _strings(values, field, path=path),
                    vocabulary,
                    path=path,
                    field=field,
                    subject=subject,
                )
            )

    for free_text in ("forbidden_keywords", "ruling_out_keywords", "required_queries"):
        if free_text in values:
            validated[free_text] = list(  # type: ignore[literal-required]
                _strings(values, free_text, path=path)
            )

    if "required_evidence_sources" in values:
        required = _within(
            _strings(values, "required_evidence_sources", path=path),
            evidence_sources(),
            path=path,
            field="required_evidence_sources",
            subject="an evidence source anything in this repository provides",
        )
        undeclared = [source for source in required if source not in available_evidence]
        if available_evidence and undeclared:
            raise FixtureError(
                path,
                "required_evidence_sources",
                f"demands {undeclared} which this scenario does not declare in "
                f"available_evidence ({sorted(available_evidence)}); no run could satisfy it",
            )
        validated["required_evidence_sources"] = list(required)

    if "golden_trajectory" in values:
        validated["golden_trajectory"] = _validate_golden(
            values["golden_trajectory"], path=path, actions=actions
        )

    if "max_investigation_loops" in values:
        ceiling = _integer(values, "max_investigation_loops", path=path)
        if not 1 <= ceiling <= MAX_INVESTIGATION_LOOPS:
            raise FixtureError(
                path,
                "max_investigation_loops",
                f"must be between 1 and {MAX_INVESTIGATION_LOOPS}; an answer key may lower "
                f"the ceiling Article II sets and never raise it, got {ceiling}",
            )
        validated["max_investigation_loops"] = ceiling

    return validated


def _validate_golden(
    document: Any, *, path: Path, actions: frozenset[str]
) -> GoldenTrajectoryDocument:
    """Return one golden trajectory, validated, or raise naming its field."""
    values = _mapping(document, path=path, field="golden_trajectory")

    ordered = _within(
        _strings(values, "ordered_actions", path=path, field="golden_trajectory.ordered_actions"),
        actions,
        path=path,
        field="golden_trajectory.ordered_actions",
        subject="a capability this repository declares",
    )
    if not ordered:
        raise FixtureError(
            path, "golden_trajectory.ordered_actions", "must name at least one action"
        )

    validated: GoldenTrajectoryDocument = {"ordered_actions": list(ordered)}
    if "matching" in values:
        validated["matching"] = _within(
            (_text(values, "matching", path=path, field="golden_trajectory.matching"),),
            TRAJECTORY_MATCHINGS,
            path=path,
            field="golden_trajectory.matching",
            subject="a supported matching strategy",
        )[0]
    for bound in ("max_edit_distance", "max_extra_actions", "max_redundancy"):
        if bound in values:
            field = f"golden_trajectory.{bound}"
            value = _integer(values, bound, path=path, field=field)
            if value < 0:
                raise FixtureError(path, field, f"must not be negative, got {value}")
            validated[bound] = value  # type: ignore[literal-required]
    return validated


__all__ = [
    "DOCUMENT_FIELD",
    "AlertDocument",
    "AnswerDocument",
    "EvidenceDocument",
    "FixtureError",
    "GoldenTrajectoryDocument",
    "RecordedResponseDocument",
    "ResponseMatchDocument",
    "ScenarioDocument",
    "read_json",
    "read_yaml",
    "validate_alert",
    "validate_answer",
    "validate_evidence",
    "validate_scenario",
]
