"""The checks that are allowed to fail the build, proved against seeded failures.

A check nobody has watched fail is a check nobody knows works. Every assertion
here seeds the exact problem it is meant to catch and then asserts the failure
names it — because "something leaked" and "a reference is broken somewhere" are
not findings anybody can act on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.mockplane.anonymise.pseudonyms import Kind
from tools.mockplane.contract import (
    ContractError,
    openapi_document,
    response_schema,
    validate,
)
from tools.mockplane.endpoints import endpoint_by_slug
from tools.mockplane.identifiers import IdentifierFileError, IdentifierList, RealIdentifier
from tools.mockplane.records import CapturedRecord, Provenance, Request
from tools.mockplane.verify import referential
from tools.mockplane.verify.coherence import awkwardness_of, distribution_of, implausibilities
from tools.mockplane.verify.identifiers import scan_text, scan_tree

pytestmark = pytest.mark.unit


def record(slug: str, body: object, arguments: dict[str, str] | None = None) -> CapturedRecord:
    return CapturedRecord(
        slug=slug,
        arguments=arguments or {},
        status=200,
        body=body,
        provenance=Provenance.GATEWAY,
        request=Request(method="GET", path=slug),
    )


# --- The adversarial scan ---------------------------------------------------------


def test_a_seeded_real_value_is_found_and_named(tmp_path: Path) -> None:
    fixture = tmp_path / "runs.json"
    fixture.write_text('{"summary": "pve-alpha could not be reached"}\n', encoding="utf-8")
    identifiers = IdentifierList.of([RealIdentifier(Kind.NODE, "pve-alpha")])

    leaks = scan_tree(tmp_path, identifiers)

    assert len(leaks) == 1
    assert leaks[0].matched == "pve-alpha"
    assert leaks[0].line == 1
    assert leaks[0].path == fixture


def test_the_pattern_net_runs_with_no_operator_list_at_all() -> None:
    leaks = scan_text(
        "the node answers on 192.168.68.149 and vault.internal",
        IdentifierList.empty(),
        path=Path("x.json"),
    )
    rules = {leak.rule for leak in leaks}
    assert "private address range" in rules
    assert "private domain suffix" in rules


def test_a_manufacturer_mac_address_is_a_leak_and_a_local_one_is_not() -> None:
    real = scan_text("b8:27:eb:4f:1a:22", IdentifierList.empty(), path=Path("x.json"))
    local = scan_text("02:1a:2b:3c:4d:5e", IdentifierList.empty(), path=Path("x.json"))
    assert [leak.rule for leak in real] == ["manufacturer MAC address"]
    assert not local


def test_an_address_from_the_documentation_range_is_not_a_leak() -> None:
    assert not scan_text("198.51.100.7", IdentifierList.empty(), path=Path("x.json"))


def test_an_email_outside_the_fictional_domain_is_a_leak() -> None:
    outside = scan_text(
        "a.person@estate.example-real.lan", IdentifierList.empty(), path=Path("x.json")
    )
    inside = scan_text(
        "avery.lockhart@example.invalid", IdentifierList.empty(), path=Path("x.json")
    )
    assert any("e-mail" in leak.rule for leak in outside)
    assert not any("e-mail" in leak.rule for leak in inside)


def test_a_credential_shaped_value_is_the_second_net() -> None:
    leaks = scan_text(
        "-----BEGIN RSA PRIVATE KEY-----", IdentifierList.empty(), path=Path("x.json")
    )
    assert [leak.rule for leak in leaks] == ["credential-shaped value"]


def test_the_scan_reads_the_file_rather_than_the_parsed_document(tmp_path: Path) -> None:
    # A leak in a key name is still a leak, and a scan over the loaded objects
    # would only see the values.
    (tmp_path / "a.json").write_text('{"pve-alpha": 1}\n', encoding="utf-8")
    leaks = scan_tree(tmp_path, IdentifierList.of([RealIdentifier(Kind.NODE, "pve-alpha")]))
    assert len(leaks) == 1


def test_an_operator_list_loads_from_a_file_outside_the_repository(tmp_path: Path) -> None:
    path = tmp_path / "real-values.txt"
    path.write_text(
        "# the values that must never appear\nnode: pve-alpha\nipv4: 192.168.68.149\n",
        encoding="utf-8",
    )
    identifiers = IdentifierList.load(path)
    assert len(identifiers) == 2
    assert identifiers.entries[0].kind is Kind.NODE


def test_no_list_at_all_is_an_empty_list_rather_than_a_failure() -> None:
    assert len(IdentifierList.load(None)) == 0


def test_a_malformed_line_says_which_line(tmp_path: Path) -> None:
    path = tmp_path / "real-values.txt"
    path.write_text("node: pve-alpha\nthis is not a pair\n", encoding="utf-8")
    with pytest.raises(IdentifierFileError) as failure:
        IdentifierList.load(path)
    assert ":2:" in str(failure.value)


def test_the_longest_value_is_replaced_first() -> None:
    identifiers = IdentifierList.of(
        [RealIdentifier(Kind.HOST, "a"), RealIdentifier(Kind.HOST, "a.b.lan")]
    )
    assert [entry.value for entry in identifiers.longest_first()] == ["a.b.lan", "a"]


# --- Referential integrity --------------------------------------------------------


def coherent() -> tuple[CapturedRecord, ...]:
    return (
        record("runs", {"runs": [{"run_id": "run-0001"}]}),
        record("estate-resources", {"resources": [{"resource_id": "ct-100"}]}),
        record("detectors", {"detectors": [{"detector_id": "quorum-margin-zero"}]}),
        record(
            "incidents",
            {
                "incidents": [
                    {
                        "incident_id": "inc-0001",
                        "detector": "quorum-margin-zero",
                        "run_id": "run-0001",
                        "subjects": ["ct-100"],
                    }
                ]
            },
        ),
    )


def test_a_coherent_dataset_has_nothing_broken() -> None:
    assert referential.broken(coherent()) == ()


def test_a_seeded_broken_reference_is_found_and_named() -> None:
    records = list(coherent())
    records[3] = record(
        "incidents",
        {
            "incidents": [
                {
                    "incident_id": "inc-0001",
                    "detector": "quorum-margin-zero",
                    "run_id": "run-9999",
                    "subjects": ["ct-100"],
                }
            ]
        },
    )
    broken = referential.broken(records)
    assert len(broken) == 1
    assert broken[0].namespace == "run"
    assert broken[0].identifier == "run-9999"
    assert "/incidents/0/run_id" in broken[0].pointer


def test_an_incident_about_a_guest_nobody_discovered_is_broken() -> None:
    records = list(coherent())
    records[1] = record("estate-resources", {"resources": []})
    broken = referential.broken(records)
    assert any(entry.namespace == "subject" for entry in broken)


def test_a_kind_beside_an_identifier_decides_which_namespace_it_points_into() -> None:
    records = (
        *coherent(),
        record(
            "audit-events",
            {
                "events": [
                    {"resource_kind": "run", "resource_id": "run-0001"},
                    {"resource_kind": "run", "resource_id": "run-9999"},
                ],
                "total": 2,
            },
        ),
    )
    broken = referential.broken(records)
    assert [entry.identifier for entry in broken] == ["run-9999"]


def test_a_write_answer_is_not_checked_because_it_describes_a_state_that_follows() -> None:
    records = (
        *coherent(),
        CapturedRecord(
            slug="investigation-start",
            arguments={},
            status=202,
            body={"run_id": "run-0007"},
            provenance=Provenance.GATEWAY,
            request=Request(method="POST", path="investigation-start"),
        ),
    )
    assert referential.broken(records) == ()


# --- Plausibility -----------------------------------------------------------------


def test_an_incident_that_closed_before_it_opened_is_caught() -> None:
    found = implausibilities(
        [
            record(
                "incidents",
                {
                    "incidents": [
                        {
                            "incident_id": "inc-0001",
                            "opened_at": "2026-08-07T10:00:00+00:00",
                            "closed_at": "2026-08-07T09:00:00+00:00",
                            "state": "closed",
                        }
                    ]
                },
            )
        ]
    )
    assert "closed before it opened" in str(found[0])


def test_a_run_that_finished_before_it_started_is_caught() -> None:
    found = implausibilities(
        [
            record(
                "runs",
                {
                    "runs": [
                        {
                            "run_id": "run-0001",
                            "started_at": "2026-08-07T10:00:00+00:00",
                            "finished_at": "2026-08-07T09:00:00+00:00",
                        }
                    ]
                },
            )
        ]
    )
    assert "completed before it started" in str(found[0])


def test_an_episode_created_before_the_run_that_produced_it_is_caught() -> None:
    found = implausibilities(
        [
            record(
                "runs",
                {"runs": [{"run_id": "run-0001", "started_at": "2026-08-07T10:00:00+00:00"}]},
            ),
            record(
                "episodes",
                {
                    "episodes": [
                        {
                            "episode_id": "ep-0001",
                            "run_id": "run-0001",
                            "occurred_at": "2026-08-07T09:00:00+00:00",
                        }
                    ]
                },
            ),
        ]
    )
    assert "before run 'run-0001' started" in str(found[0])


def test_out_of_order_turns_are_caught() -> None:
    found = implausibilities(
        [
            record(
                "run-replay",
                {
                    "turns": [
                        {"ordinal": 2, "occurred_at": "2026-08-07T10:00:00+00:00"},
                        {"ordinal": 1, "occurred_at": "2026-08-07T09:00:00+00:00"},
                    ]
                },
            )
        ]
    )
    assert found


# --- Distribution and awkwardness -------------------------------------------------


def estate() -> tuple[CapturedRecord, ...]:
    return (
        record(
            "estate-resources",
            {
                "resources": [
                    {
                        "resource_id": "ct-100",
                        "kind": "container",
                        "parent_name": "node01",
                        "health": "running",
                        "attributes": {"backed_up": False},
                    },
                    {
                        "resource_id": "vm-101",
                        "kind": "virtual-machine",
                        "parent_name": "node02",
                        "health": "stopped",
                        "attributes": {"backed_up": True},
                    },
                ]
            },
        ),
        record(
            "estate-storage",
            {
                "datastores": [{"name": "store-a", "status": "unknown", "used_percent": None}],
                "thin_pools": [],
                "volumes": [{"volume_id": "vm-100-disk-0", "used_percent": 99.6}],
            },
        ),
        record(
            "estate-backups",
            {"jobs": [{"job_id": "backup-1", "enabled": False, "uncovered": 55}]},
        ),
        record(
            "estate-nodes", {"nodes": [{"node_id": "node-node01", "failed_units": ["a.mount"]}]}
        ),
    )


def test_the_awkward_properties_are_each_detected() -> None:
    awkward = awkwardness_of(estate())
    assert awkward.missing == ()
    assert bool(awkward) is True


def test_a_tidied_dataset_reports_exactly_what_it_lost() -> None:
    tidied = (
        record(
            "estate-resources",
            {
                "resources": [
                    {
                        "resource_id": "ct-100",
                        "kind": "container",
                        "node": "node01",
                        "state": "running",
                        "backed_up": True,
                    }
                ]
            },
        ),
        record("estate-storage", {"datastores": [], "thin_pools": [], "volumes": []}),
        record("estate-backups", {"jobs": [{"job_id": "b", "enabled": True, "uncovered": 0}]}),
        record("estate-nodes", {"nodes": [{"node_id": "node-node01", "failed_units": []}]}),
    )
    assert len(awkwardness_of(tidied).missing) == 5


def test_the_distribution_notices_counts_ratios_and_node_skew() -> None:
    shape = distribution_of(estate())
    assert shape.resources_by_kind == {"container": 1, "virtual-machine": 1}
    assert shape.resources_by_node == {"node01": 1, "node02": 1}
    assert shape.states == {"running": 1, "stopped": 1}
    assert 99.6 in shape.percentages


# --- The contract validator -------------------------------------------------------


def test_a_valid_payload_validates() -> None:
    schema, document = response_schema(endpoint_by_slug("memory-stats"))
    assert validate({"episode_count": 5}, schema, document) == ()


def test_a_missing_required_field_is_named() -> None:
    schema, document = response_schema(endpoint_by_slug("memory-stats"))
    violations = validate({}, schema, document)
    assert "/episode_count" in violations[0].pointer
    assert "required" in violations[0].message


def test_a_wrong_type_names_the_field_and_both_types() -> None:
    schema, document = response_schema(endpoint_by_slug("memory-stats"))
    violations = validate({"episode_count": "five"}, schema, document)
    assert violations[0].pointer == "/episode_count"
    assert "integer" in violations[0].message and "string" in violations[0].message


def test_a_nested_record_is_named_by_its_index() -> None:
    schema, document = response_schema(endpoint_by_slug("runs"))
    violations = validate({"runs": [{"run_id": "r", "trigger": "alert"}]}, schema, document)
    assert violations[0].pointer == "/runs/0/status"


def test_a_nullable_field_accepts_both() -> None:
    schema, document = response_schema(endpoint_by_slug("runs"))
    body = {"runs": [{"run_id": "r", "trigger": "alert", "status": "running", "summary": None}]}
    assert validate(body, schema, document) == ()


def test_a_boolean_is_not_an_integer() -> None:
    schema, document = response_schema(endpoint_by_slug("memory-stats"))
    assert validate({"episode_count": True}, schema, document)


def test_an_endpoint_the_document_does_not_describe_is_an_error() -> None:
    from tools.mockplane.endpoints import ConsoleEndpoint, EndpointSource

    invented = ConsoleEndpoint(
        method="GET", path="/v1/nowhere", slug="nowhere", source=EndpointSource.GATEWAY, summary=""
    )
    with pytest.raises(ContractError) as failure:
        response_schema(invented)
    assert "/v1/nowhere" in str(failure.value)


def test_the_committed_document_is_what_the_application_generates() -> None:
    from tools.mockplane.contract import generated_openapi_document

    assert openapi_document() == generated_openapi_document(), (
        "the committed OpenAPI document has drifted from the routes; "
        "run 'python -m tools.mockplane contract' and rebuild the fixtures"
    )
