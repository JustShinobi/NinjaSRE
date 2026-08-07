"""The committed dataset as a whole: referentially complete, plausible, and awkward.

A dataset that validates against the contract can still be a dataset nobody can
design against — every reference dangling, every incident about a guest that is
not in the estate, every percentage rounded to something tidy. These are the
assertions that keep it worth having.
"""

from __future__ import annotations

from pathlib import Path

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


def test_rebuilding_the_dataset_reproduces_what_is_committed(tmp_path: Path) -> None:
    build.write_all(tmp_path)
    for scenario in build.BUILT_SCENARIOS:
        committed = sorted(scenarios.scenario_files(scenario))
        rebuilt = sorted((tmp_path / "scenarios" / scenario).glob("*.json"))
        assert [path.name for path in committed] == [path.name for path in rebuilt], scenario
        for first, second in zip(committed, rebuilt):
            assert first.read_bytes() == second.read_bytes(), (
                f"{first.name} in {scenario} differs from what the builder produces; "
                f"run 'python -m tools.mockplane build'"
            )


def test_two_builds_of_one_scenario_are_byte_identical() -> None:
    first = build.processed_for("populated")
    second = build.processed_for("populated")
    assert dumps([record.as_json() for record in first.records]) == dumps(
        [record.as_json() for record in second.records]
    )


def test_the_committed_files_are_written_in_the_canonical_form() -> None:
    for path in scenarios.scenario_files("populated"):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), f"{path.name} has no trailing newline"
        import json

        assert dumps(json.loads(text)) == text, (
            f"{path.name} is not in the canonical form, so a rebuild would churn it"
        )
