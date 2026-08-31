"""The committed dataset as a whole: referentially complete, plausible, and awkward.

A dataset that validates against the contract can still be a dataset nobody can
design against — every reference dangling, every incident about a guest that is
not in the estate, every percentage rounded to something tidy. These are the
assertions that keep it worth having.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from config.constants.fixtures import FIXTURE_SCENARIO_NAMES
from tools.mockplane import scenarios
from tools.mockplane.anonymise.pseudonyms import PSEUDONYM_DOMAIN
from tools.mockplane.dataset import build, profile
from tools.mockplane.identifiers import IdentifierList
from tools.mockplane.paths import fixture_root
from tools.mockplane.records import dumps
from tools.mockplane.verify import referential
from tools.mockplane.verify.coherence import awkwardness_of, distribution_of, implausibilities
from tools.mockplane.verify.identifiers import scan_tree

pytestmark = pytest.mark.contract


@pytest.mark.parametrize("scenario", FIXTURE_SCENARIO_NAMES)
def test_every_reference_in_every_scenario_resolves(scenario: str) -> None:
    broken = referential.broken(scenarios.load(scenario).all_records())
    assert not broken, "\n".join(str(reference) for reference in broken)


@pytest.mark.parametrize("scenario", FIXTURE_SCENARIO_NAMES)
def test_every_scenario_reads_as_a_coherent_history(scenario: str) -> None:
    found = implausibilities(scenarios.load(scenario).all_records())
    assert not found, "\n".join(str(entry) for entry in found)


def test_nothing_real_survives_in_the_committed_tree() -> None:
    # The pattern net, which runs on every clone with no configuration at all.
    # The operator's list of actual values is the second net and is supplied at
    # scan time — ``python -m tools.mockplane verify --identifiers <file>``.
    leaks = scan_tree(fixture_root(), IdentifierList.empty())
    assert not leaks, "\n".join(str(leak) for leak in leaks)


def test_the_fictional_deployment_answers_on_a_domain_that_cannot_resolve() -> None:
    assert PSEUDONYM_DOMAIN.endswith(".invalid")


# --- The properties nobody invents ------------------------------------------------


def test_the_awkward_properties_survived_into_the_committed_dataset() -> None:
    awkward = awkwardness_of(scenarios.load("populated").all_records())
    assert not awkward.missing, "the dataset has been tidied and no longer has: " + ", ".join(
        awkward.missing
    )


def test_the_estate_keeps_the_counts_and_the_ratio_that_were_measured() -> None:
    shape = distribution_of(scenarios.load("populated").all_records())
    assert shape.resources_by_kind["container"] == profile.TOTAL_GUESTS - profile.VIRTUAL_MACHINES
    assert shape.resources_by_kind["virtual-machine"] == profile.VIRTUAL_MACHINES
    assert shape.resources_by_kind["node"] == 2


def test_the_load_is_still_skewed_onto_one_node() -> None:
    shape = distribution_of(scenarios.load("populated").all_records())
    primary = shape.resources_by_node[profile.PRIMARY_NODE]
    secondary = shape.resources_by_node[profile.SECONDARY_NODE]
    assert primary > secondary, "the node skew has been evened out, which was the point of it"


def test_a_guest_is_above_its_own_ceiling_while_its_datastore_reads_comfortable() -> None:
    storage = scenarios.load("populated").lookup("estate-storage", {})
    assert storage is not None
    worst_volume = max(entry["used_percent"] for entry in storage.body["volumes"])
    local = next(
        entry
        for entry in storage.body["datastores"]
        if entry["name"] == "local-lvm" and entry["node"] == profile.SECONDARY_NODE
    )
    assert worst_volume > 99.0
    assert local["used_percent"] < 90.0, (
        "the distinction a datastore-level threshold cannot make has been lost"
    )


def test_the_pool_with_the_metadata_pressure_still_reads_comfortable_on_data() -> None:
    storage = scenarios.load("populated").lookup("estate-storage", {})
    assert storage is not None
    pool = next(entry for entry in storage.body["thin_pools"] if entry["metadata_percent"] > 30)
    assert pool["data_percent"] < 80.0


def test_a_backup_job_exists_and_is_disabled_and_guests_are_uncovered() -> None:
    backups = scenarios.load("populated").lookup("estate-backups", {})
    assert backups is not None
    disabled = [job for job in backups.body["jobs"] if not job["enabled"]]
    assert disabled, "the disabled job has been enabled, which removes the finding"
    assert max(job["uncovered"] for job in backups.body["jobs"]) > 0


def test_two_datastores_still_answer_unknown() -> None:
    storage = scenarios.load("populated").lookup("estate-storage", {})
    assert storage is not None
    unknown = [entry for entry in storage.body["datastores"] if entry["status"] == "unknown"]
    assert len(unknown) == 2
    assert all(entry["used_percent"] is None for entry in unknown)


def test_the_quorum_finding_is_in_the_dataset() -> None:
    incidents = scenarios.load("populated").lookup("incidents", {})
    assert incidents is not None
    detectors = {incident["detector"] for incident in incidents.body["incidents"]}
    assert "quorum-margin-zero" in detectors


def test_a_node_still_has_a_set_of_failed_units() -> None:
    nodes = scenarios.load("populated").lookup("estate-nodes", {})
    assert nodes is not None
    assert max(len(node["failed_units"]) for node in nodes.body["nodes"]) >= 9


# --- Determinism of what is committed ---------------------------------------------


#: The one correlation key `_recurring_incidents`
#: (`tools.mockplane.capture.projection`) times from the real clock rather
#: than from `profile.CAPTURED_AT`, so its three occurrences keep landing
#: inside the Painel's 48h subject window instead of ageing out of it —
#: deliberately, the one exception to every other byte in this dataset
#: being reproducible forever.
#: `_recurring_incidents` (`tools.mockplane.capture.projection`) marks its
#: three occurrences with this string in their `correlation_key`, timed
#: from the real clock on purpose so they keep landing inside the Painel's
#: 48h subject window instead of ageing out of it -- the one deliberate
#: exception to every other byte in this dataset being reproducible
#: forever. `_PLACEHOLDER` is what both reproducibility checks below
#: substitute for the timestamps that fact makes non-reproducible.
_WALL_CLOCK_RELATIVE_MARKER = "RedisExporterDown"
_PLACEHOLDER = "<wall-clock relative, see projection.py>"


def _is_recurring(correlation_key: object) -> bool:
    return _WALL_CLOCK_RELATIVE_MARKER in str(correlation_key)


def _body_without_wall_clock_timestamps(slug: str | None, body: Any) -> Any:
    """Return one record's own `body`, the recurring subject's timestamps blanked.

    Two slugs carry one: `incidents`' own `incidents[].opened_at`, and
    `incident-detail`'s `incident.opened_at` plus every `timeline[].at` --
    the same fact, told three times over because three different screens
    read it from three different shapes.
    """
    if not isinstance(body, dict):
        return body
    if slug == "incidents":
        incidents = [
            {**incident, "opened_at": _PLACEHOLDER}
            if _is_recurring(incident.get("correlation_key"))
            else incident
            for incident in body.get("incidents", ())
        ]
        return {**body, "incidents": incidents}
    if slug == "incident-detail":
        incident = body.get("incident")
        if not isinstance(incident, dict) or not _is_recurring(incident.get("correlation_key")):
            return body
        timeline = [
            {**entry, "at": _PLACEHOLDER} if isinstance(entry, dict) and "at" in entry else entry
            for entry in body.get("timeline", ())
        ]
        return {**body, "incident": {**incident, "opened_at": _PLACEHOLDER}, "timeline": timeline}
    return body


def _file_without_wall_clock_timestamps(data: bytes) -> bytes:
    """Return one committed fixture file, its own body blanked the same way."""
    try:
        payload = json.loads(data)
    except ValueError:
        return data
    if not isinstance(payload, dict):
        return data
    slug = payload.get("slug")
    responses = [
        {**response, "body": _body_without_wall_clock_timestamps(slug, response.get("body"))}
        for response in payload.get("responses", ())
    ]
    return dumps({**payload, "responses": responses}).encode("utf-8")


def test_rebuilding_the_dataset_reproduces_what_is_committed(tmp_path: Path) -> None:
    build.write_all(tmp_path)
    for scenario in build.BUILT_SCENARIOS:
        committed = sorted(scenarios.scenario_files(scenario))
        rebuilt = sorted((tmp_path / "scenarios" / scenario).glob("*.json"))
        assert [path.name for path in committed] == [path.name for path in rebuilt], scenario
        for first, second in zip(committed, rebuilt):
            assert _file_without_wall_clock_timestamps(
                first.read_bytes()
            ) == _file_without_wall_clock_timestamps(second.read_bytes()), (
                f"{first.name} in {scenario} differs from what the builder produces; "
                f"run 'python -m tools.mockplane build'"
            )


def _records_without_wall_clock_timestamps(records: list[dict[str, Any]]) -> bytes:
    """Return one build's flat record list, each body blanked the same way.

    `CapturedRecord.as_json()`'s own shape holds `body` directly rather than
    wrapped in a file's `responses` list, so this calls the same body-level
    helper `_file_without_wall_clock_timestamps` calls per response, once
    per record instead.
    """
    normalised = [
        {
            **record,
            "body": _body_without_wall_clock_timestamps(record.get("slug"), record.get("body")),
        }
        for record in records
    ]
    return dumps(normalised).encode("utf-8")


def test_two_builds_of_one_scenario_are_byte_identical() -> None:
    first = build.processed_for("populated")
    second = build.processed_for("populated")
    first_json = [record.as_json() for record in first.records]
    second_json = [record.as_json() for record in second.records]
    assert _records_without_wall_clock_timestamps(
        first_json
    ) == _records_without_wall_clock_timestamps(second_json)


def test_the_committed_files_are_written_in_the_canonical_form() -> None:
    for path in scenarios.scenario_files("populated"):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), f"{path.name} has no trailing newline"
        import json

        assert dumps(json.loads(text)) == text, (
            f"{path.name} is not in the canonical form, so a rebuild would churn it"
        )
