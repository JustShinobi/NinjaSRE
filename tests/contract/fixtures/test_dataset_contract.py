"""Every committed fixture, against the API document, and every endpoint covered.

This is the check that keeps the dataset from rotting. A route whose response
model changes invalidates a fixture, and the failure names the endpoint and the
field rather than being discovered by a screen that renders a dash where a
number should be.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from config.constants.fixtures import FIXTURE_SCENARIO_NAMES
from tools.mockplane import scenarios
from tools.mockplane.contract import (
    ContractError,
    openapi_document,
    projected_document,
    response_schema,
    validate,
)
from tools.mockplane.dataset.build import uncovered_slugs
from tools.mockplane.endpoints import CONSOLE_ENDPOINTS, endpoint_by_slug, projected_endpoints
from tools.mockplane.records import CapturedRecord

pytestmark = pytest.mark.contract


def _validatable(record: CapturedRecord) -> bool:
    endpoint = endpoint_by_slug(record.slug)
    return not endpoint.streaming and record.status < 400


# --- Coverage ---------------------------------------------------------------------


def test_every_console_consumed_endpoint_has_a_fixture() -> None:
    missing = uncovered_slugs()
    assert not missing, (
        "these endpoints are consumed by the console and nothing in the dataset "
        f"answers them: {', '.join(missing)}"
    )


def test_the_default_scenario_answers_every_endpoint_by_name() -> None:
    served = scenarios.load("populated").slugs()
    missing = sorted(endpoint.slug for endpoint in CONSOLE_ENDPOINTS if endpoint.slug not in served)
    assert not missing, f"populated has no fixture for: {', '.join(missing)}"


def test_a_scenario_with_a_missing_fixture_is_reported_by_name(tmp_path: Path) -> None:
    # Seeded: copy the default scenario, delete one endpoint's file, and assert
    # the coverage check names exactly that endpoint.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"default": "populated", "scenarios": [{"name": "populated", "description": "a copy"}]}
        ),
        encoding="utf-8",
    )
    source = scenarios.scenario_files("populated")
    destination = tmp_path / "scenarios" / "populated"
    destination.mkdir(parents=True)
    for path in source:
        if path.stem == "approvals":
            continue
        (destination / path.name).write_bytes(path.read_bytes())

    served = scenarios.load("populated", tmp_path).slugs()
    missing = [endpoint.slug for endpoint in CONSOLE_ENDPOINTS if endpoint.slug not in served]
    assert missing == ["approvals"]


# --- Contract fidelity ------------------------------------------------------------


@pytest.mark.parametrize("scenario", FIXTURE_SCENARIO_NAMES)
def test_every_fixture_validates_against_the_api_document(scenario: str) -> None:
    failures: list[str] = []
    for record in scenarios.load(scenario).all_records():
        if not _validatable(record):
            continue
        endpoint = endpoint_by_slug(record.slug)
        try:
            schema, document = response_schema(endpoint, record.status)
        except ContractError as failure:
            failures.append(str(failure))
            continue
        failures.extend(
            f"{endpoint.method} {endpoint.path} {record.arguments or ''}: {violation}"
            for violation in validate(record.body, schema, document)
        )
    assert not failures, "\n".join(failures)


def test_incident_views_carry_an_origin_scoped_correlation_key() -> None:
    """Every incident response preserves the domain key that raised it."""
    failures: list[str] = []
    for scenario in FIXTURE_SCENARIO_NAMES:
        for record in scenarios.load(scenario).all_records():
            if record.slug == "incidents":
                body = record.body if isinstance(record.body, dict) else {}
                candidates = body.get("incidents", [])
            elif record.slug == "incident-detail":
                body = record.body if isinstance(record.body, dict) else {}
                candidates = [body.get("incident")]
            else:
                continue
            for incident in candidates if isinstance(candidates, list) else []:
                if not isinstance(incident, dict):
                    continue
                correlation_key = incident.get("correlation_key", "")
                origin = str(incident.get("origin", ""))
                detector = str(incident.get("detector", ""))
                expected_prefix = {
                    "detector": f"detector:{detector}",
                    "alert": f"alert:{detector}:",
                }.get(origin, "")
                if not isinstance(correlation_key, str) or not correlation_key:
                    failures.append(f"{scenario}/{record.slug}: correlation_key is empty")
                elif expected_prefix and (
                    correlation_key != expected_prefix
                    if origin == "detector"
                    else not correlation_key.startswith(expected_prefix)
                ):
                    failures.append(
                        f"{scenario}/{record.slug}: {origin} incident has "
                        f"correlation_key {correlation_key!r}, expected {expected_prefix!r}"
                    )
    assert not failures, "\n".join(failures)


def test_every_principal_kind_is_one_the_backend_actually_declares() -> None:
    """``kind`` is a plain ``str`` on the wire, so schema validation alone never
    catches a value the real ``PrincipalKind`` enum does not have — the gap that
    let this dataset serve ``"person"``/``"machine"`` while the backend only
    ever emits ``"user"``/``"service_account"``, invisible until a screen
    rendered the wrong fallback for a value nothing here ever served.
    """
    from platform.persistence.ports import PrincipalKind

    allowed = {member.value for member in PrincipalKind}
    offending: list[str] = []
    for scenario in FIXTURE_SCENARIO_NAMES:
        for record in scenarios.load(scenario).all_records():
            if record.slug == "principal":
                people: list[Any] = [record.body]
            elif record.slug == "principals":
                users = record.body.get("users") if isinstance(record.body, dict) else None
                people = users if isinstance(users, list) else []
            else:
                continue
            for person in people:
                kind = person.get("kind") if isinstance(person, dict) else None
                if kind is not None and kind not in allowed:
                    offending.append(f"{scenario}/{record.slug}: {kind!r}")
    assert not offending, (
        f"a fixture serves a principal kind the real backend never emits: {offending}"
    )


def test_every_actor_kind_is_one_the_backend_actually_declares() -> None:
    """``actor_kind`` is a plain ``str`` on the wire too, so schema validation
    alone never catches a value the real ``ActorKind`` enum does not have — the
    same gap ``test_every_principal_kind_is_one_the_backend_actually_declares``
    closes for principals, here for the audit trail's own actor field.
    """
    from platform.persistence.ports import ActorKind

    allowed = {member.value for member in ActorKind}
    offending: list[str] = []
    for scenario in FIXTURE_SCENARIO_NAMES:
        for record in scenarios.load(scenario).all_records():
            if record.slug != "audit-events":
                continue
            events = record.body.get("events") if isinstance(record.body, dict) else None
            for event in events if isinstance(events, list) else []:
                kind = event.get("actor_kind") if isinstance(event, dict) else None
                if kind is not None and kind not in allowed:
                    offending.append(f"{scenario}/{record.slug}: {kind!r}")
    assert not offending, (
        f"a fixture serves an actor kind the real backend never emits: {offending}"
    )


def test_every_audit_outcome_is_one_the_backend_actually_declares() -> None:
    """The same gap, for the audit trail's own outcome field.

    ``outcome`` is a plain ``str`` on the wire too, so schema validation alone
    never catches a value the real ``AuditOutcome`` enum does not have — the
    gap that let this dataset serve ``"succeeded"`` for seven of its eight
    events, a word the real backend never emits for an audit outcome.
    """
    from platform.persistence.ports import AuditOutcome

    allowed = {member.value for member in AuditOutcome}
    offending: list[str] = []
    for scenario in FIXTURE_SCENARIO_NAMES:
        for record in scenarios.load(scenario).all_records():
            if record.slug != "audit-events":
                continue
            events = record.body.get("events") if isinstance(record.body, dict) else None
            for event in events if isinstance(events, list) else []:
                outcome = event.get("outcome") if isinstance(event, dict) else None
                if outcome is not None and outcome not in allowed:
                    offending.append(f"{scenario}/{record.slug}: {outcome!r}")
    assert not offending, (
        f"a fixture serves an audit outcome the real backend never emits: {offending}"
    )


def _side_effect_level_pointers(value: Any, *, pointer: str = "") -> list[tuple[str, Any]]:
    """Return every ``(pointer, value)`` pair where a key is ``side_effect_level``.

    Recursive, because the field sits at a different depth in each slug that
    carries it: a top-level field on an approval, nested under ``entries`` in
    the catalogue, under ``tools`` in the capability listing, and under
    ``detail`` on an audit event describing one. A value the backend cannot say
    is exactly as wrong wherever in the body it is nested.
    """
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child_pointer = f"{pointer}/{key}"
            if key == "side_effect_level":
                found.append((child_pointer, nested))
            else:
                found.extend(_side_effect_level_pointers(nested, pointer=child_pointer))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_side_effect_level_pointers(item, pointer=f"{pointer}/{index}"))
    return found


def test_every_side_effect_level_is_one_the_backend_actually_declares() -> None:
    """``side_effect_level`` is a plain ``str`` on the wire too, so schema
    validation alone never catches a value the real ``SIDE_EFFECT_LEVELS`` tuple
    does not have — the gap that let this dataset serve ``"write"``, a sixth
    level the backend has never declared, for every capability that was not a
    plain read, leaving the whole upper half of the scale exercised by nothing.
    """
    from config.constants.security import SIDE_EFFECT_LEVELS

    allowed = set(SIDE_EFFECT_LEVELS)
    offending: list[str] = []
    for scenario in FIXTURE_SCENARIO_NAMES:
        for record in scenarios.load(scenario).all_records():
            for pointer, level in _side_effect_level_pointers(record.body):
                if level is not None and level not in allowed:
                    offending.append(f"{scenario}/{record.slug}{pointer}: {level!r}")
    assert not offending, (
        f"a fixture serves a side-effect level the real backend never declares: {offending}"
    )


def test_a_seeded_contract_change_fails_naming_the_endpoint_and_the_field() -> None:
    # What a route change looks like from here: the document gains a required
    # field the fixture does not carry.
    document: dict[str, Any] = json.loads(json.dumps(openapi_document()))
    document["components"]["schemas"]["InvestigationSummary"]["required"].append("closed_by")
    document["components"]["schemas"]["InvestigationSummary"]["properties"]["closed_by"] = {
        "type": "string"
    }

    endpoint = endpoint_by_slug("runs")
    schema = document["paths"][endpoint.path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    record = scenarios.load("populated").lookup("runs", {})
    assert record is not None

    violations = validate(record.body, schema, document)

    assert violations, "a contract change that invalidates a fixture went unnoticed"
    assert any("closed_by" in violation.pointer for violation in violations)
    assert any("/runs/0/" in violation.pointer for violation in violations)


def test_the_projected_document_describes_exactly_the_projected_endpoints() -> None:
    declared = set(projected_document()["paths"])
    expected = {endpoint.path for endpoint in projected_endpoints()}
    assert declared == expected, (
        "the projected schemas and the endpoint catalogue disagree; when one of "
        "these endpoints is really served, delete it from both"
    )


def test_a_projected_path_is_absent_from_the_gateways_own_document() -> None:
    served = set(openapi_document()["paths"])
    assert not served & set(projected_document()["paths"])


def test_the_streaming_endpoint_is_not_validated_as_a_body() -> None:
    record = scenarios.load("populated").lookup("run-stream", {"run_id": "run-0003"})
    assert record is not None
    assert endpoint_by_slug(record.slug).streaming is True
    assert isinstance(record.body["events"], list)


# --- Provenance in the committed dataset ------------------------------------------


def test_every_committed_record_states_where_it_came_from() -> None:
    for record in scenarios.load("populated").all_records():
        assert record.provenance, f"{record.slug} does not say how it was obtained"


def test_no_projected_endpoint_carries_a_record_attributed_to_the_gateway() -> None:
    projected = {endpoint.slug for endpoint in projected_endpoints()}
    offending = [
        record.slug
        for record in scenarios.load("populated").all_records()
        if record.slug in projected and not record.is_projected
    ]
    assert not offending, (
        "a projected endpoint holds a record attributed to the gateway, which is "
        f"a fixture somebody will one day read as evidence the endpoint worked: {offending}"
    )
