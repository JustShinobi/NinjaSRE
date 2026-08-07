"""Anonymisation, against a capture that carries everything it must not emit.

The synthetic capture below is deliberately nasty: a hostname in a log line, an
address inside a URL, a private key in a field nobody would think to name, a
guest whose name appears in three unrelated documents, and a token expiring next
year. Every one of those is a case that has broken a pipeline like this before.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tools.mockplane.anonymise.pipeline import process
from tools.mockplane.anonymise.pseudonyms import (
    PSEUDONYM_DOMAIN,
    Kind,
    MissingPseudonymKey,
    PseudonymBook,
)
from tools.mockplane.anonymise.redaction import (
    REMOVED,
    anonymise,
    replace_in_text,
    should_remove,
)
from tools.mockplane.anonymise.timeshift import offset_for, shift, timestamps_in
from tools.mockplane.identifiers import IdentifierList, RealIdentifier
from tools.mockplane.records import CapturedRecord, Provenance, Request

pytestmark = pytest.mark.unit

REAL = IdentifierList.of(
    [
        RealIdentifier(Kind.NODE, "pve-alpha"),
        RealIdentifier(Kind.NODE, "pve-beta"),
        RealIdentifier(Kind.GUEST, "ledgerd"),
        RealIdentifier(Kind.DOMAIN, "estate.example-real.lan"),
        RealIdentifier(Kind.PERSON, "A Real Person"),
    ]
)


def book() -> PseudonymBook:
    return PseudonymBook(key=b"a key that stays with the operator")


def capture() -> tuple[CapturedRecord, ...]:
    def record(slug: str, body: object) -> CapturedRecord:
        return CapturedRecord(
            slug=slug,
            arguments={},
            status=200,
            body=body,
            provenance=Provenance.GATEWAY,
            request=Request(method="GET", path=slug),
        )

    return (
        record(
            "estate-nodes",
            {
                "nodes": [
                    {
                        "node": "pve-alpha",
                        "hostname": "pve-alpha.estate.example-real.lan",
                        "address": "192.168.68.149",
                        "mac": "b8:27:eb:4f:1a:22",
                        "started_at": "2026-08-05T09:00:00+00:00",
                        "root_password": "hunter2",
                        "ssh_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC" + "x" * 60,
                        "failed_units": ["mnt-archive.mount"],
                    }
                ]
            },
        ),
        record(
            "runs",
            {
                "runs": [
                    {
                        "run_id": "run-0001",
                        "started_at": "2026-08-05T09:05:00+00:00",
                        "summary": "ledgerd on pve-alpha could not reach "
                        "https://estate.example-real.lan/api; A Real Person acknowledged it",
                        "owner": "a.person@estate.example-real.lan",
                    }
                ]
            },
        ),
        record(
            "tokens",
            {
                "tokens": [
                    {
                        "token_id": "tok-0001",
                        "name": "console",
                        "expires_at": "2027-06-28T09:00:00+00:00",
                        "secret": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop",
                    }
                ]
            },
        ),
    )


# --- Pseudonyms -------------------------------------------------------------------


def test_the_same_input_yields_the_same_pseudonym_every_time() -> None:
    first = book().of(Kind.NODE, "pve-alpha")
    second = book().of(Kind.NODE, "pve-alpha")
    assert first == second


def test_two_inputs_never_share_one_pseudonym() -> None:
    shared = book()
    seen = {shared.of(Kind.GUEST, f"guest-{index}") for index in range(400)}
    assert len(seen) == 400, "two real entities were merged into one pseudonym"


def test_a_different_key_yields_a_different_pseudonym() -> None:
    assert PseudonymBook(key=b"one").of(Kind.NODE, "pve-alpha") != PseudonymBook(key=b"two").of(
        Kind.NODE, "pve-alpha"
    )


def test_the_output_does_not_carry_the_input() -> None:
    pseudonym = book().of(Kind.GUEST, "ledgerd")
    assert "ledgerd" not in pseudonym


def test_addresses_are_drawn_from_the_ranges_reserved_for_documentation() -> None:
    assert book().of(Kind.IPV4, "192.168.68.149").startswith("198.51.100.")
    assert book().of(Kind.IPV6, "fd00::1").startswith("2001:db8:")
    assert book().of(Kind.MAC, "b8:27:eb:4f:1a:22").startswith("02:")


def test_an_address_is_never_left_as_it_was() -> None:
    assert book().of(Kind.IPV4, "192.168.68.149") != "192.168.68.149"


def test_a_principal_is_an_identifier_and_an_address_is_an_address() -> None:
    assert "@" not in book().of(Kind.PRINCIPAL, "user-operator")
    assert book().of(Kind.EMAIL, "a@b.lan").endswith(PSEUDONYM_DOMAIN)


def test_no_key_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(MissingPseudonymKey) as failure:
        PseudonymBook.from_environment({})
    assert "NINJASRE_PSEUDONYM_KEY" in str(failure.value)


# --- One value, one pseudonym, everywhere -----------------------------------------


def test_one_real_value_maps_to_one_pseudonym_across_every_record() -> None:
    shared = book()
    processed = process(capture(), book=shared, identifiers=REAL)
    node = shared.of(Kind.NODE, "pve-alpha")
    summary = processed.records[1].body["runs"][0]["summary"]
    assert node in summary, "the same host is named differently in two records"


def test_a_hostname_inside_free_text_is_replaced_too() -> None:
    replaced = replace_in_text(
        "ledgerd on pve-alpha could not reach https://estate.example-real.lan/api",
        book(),
        REAL,
    )
    for value in ("ledgerd", "pve-alpha", "estate.example-real.lan"):
        assert value not in replaced


def test_a_longer_value_is_replaced_before_the_shorter_one_it_contains() -> None:
    identifiers = IdentifierList.of(
        [
            RealIdentifier(Kind.HOST, "alpha"),
            RealIdentifier(Kind.HOST, "alpha.estate.example-real.lan"),
        ]
    )
    replaced = replace_in_text("reached alpha.estate.example-real.lan today", book(), identifiers)
    assert "alpha" not in replaced


def test_an_address_nobody_declared_is_still_replaced() -> None:
    replaced = replace_in_text("the node answers on 10.4.9.31", book(), IdentifierList.empty())
    assert "10.4.9.31" not in replaced
    assert "198.51.100." in replaced


def test_a_private_domain_suffix_is_replaced_without_being_declared() -> None:
    replaced = replace_in_text("reached vault.internal", book(), IdentifierList.empty())
    assert "vault.internal" not in replaced


def test_loopback_is_left_alone_because_it_names_nobody() -> None:
    assert "127.0.0.1" in replace_in_text("bound to 127.0.0.1", book(), IdentifierList.empty())


# --- Credentials are removed, not renamed -----------------------------------------


def test_a_credential_field_is_removed_rather_than_pseudonymised() -> None:
    processed = process(capture(), book=book(), identifiers=REAL)
    node = processed.records[0].body["nodes"][0]
    assert node["root_password"] == REMOVED
    assert node["ssh_key"] == REMOVED


def test_a_credential_shaped_value_in_a_field_nobody_expected_is_removed() -> None:
    anonymised = anonymise(
        {"note": "-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----"},
        book(),
        IdentifierList.empty(),
    )
    assert anonymised["note"] == REMOVED


def test_a_connection_string_carrying_a_password_is_removed() -> None:
    anonymised = anonymise(
        {"dsn": "postgresql://someone:s3cret@db.internal:5432/app"}, book(), IdentifierList.empty()
    )
    assert anonymised["dsn"] == REMOVED


def test_a_cloud_init_block_is_removed() -> None:
    anonymised = anonymise({"cicustom": "#cloud-config\nusers: []"}, book(), IdentifierList.empty())
    assert anonymised["cicustom"] == REMOVED


def test_a_collection_named_after_a_credential_is_not_a_credential() -> None:
    # ``tokens`` is a list of records and ``token_id`` names one. Removing
    # either would break every reference to it and protect nothing.
    processed = process(capture(), book=book(), identifiers=REAL)
    tokens = processed.records[2].body["tokens"]
    assert isinstance(tokens, list)
    assert tokens[0]["token_id"] == "tok-0001"
    assert tokens[0]["secret"] == REMOVED


def test_the_pipeline_reports_where_it_removed_something() -> None:
    processed = process(capture(), book=book(), identifiers=REAL)
    assert any("root_password" in pointer for pointer in processed.removed)


def test_a_field_naming_a_thing_is_not_the_thing() -> None:
    assert should_remove("api_token", "sk-abcdefghijklmnop") is True
    assert should_remove("token_id", "tok-0001") is False, "an identifier is not a credential"
    assert should_remove("total_tokens", 1840) is False, "a count is not a credential"
    assert should_remove("tokens", [{"token_id": "tok-0001"}]) is False


# --- Time -------------------------------------------------------------------------


def test_every_interval_survives_the_shift() -> None:
    document = {
        "first": "2026-08-05T09:00:00+00:00",
        "second": "2026-08-05T09:05:00+00:00",
        "third": "2026-08-07T09:41:00+00:00",
    }
    moved = shift(document, timedelta(hours=2, minutes=19))
    before = [datetime.fromisoformat(value) for value in document.values()]
    after = [datetime.fromisoformat(value) for value in moved.values()]
    assert [b - a for a, b in zip(before, before[1:])] == [b - a for a, b in zip(after, after[1:])]


def test_the_anchor_decides_the_offset_rather_than_the_furthest_timestamp() -> None:
    # A token expiring next year must not drag the whole history back with it.
    document = {"now": "2026-08-07T09:41:00+00:00", "expires": "2027-06-28T09:00:00+00:00"}
    target = datetime.fromisoformat("2026-08-07T12:00:00+00:00")
    anchored = offset_for(document, target, anchor=datetime.fromisoformat(document["now"]))
    assert anchored == timedelta(hours=2, minutes=19)


def test_a_document_with_no_timestamps_does_not_depend_on_the_clock() -> None:
    assert offset_for({"a": 1}) == timedelta(0)


def test_the_shift_keeps_the_spelling_each_timestamp_was_written_in() -> None:
    moved = shift({"z": "2026-08-05T09:00:00Z", "o": "2026-08-05T09:00:00+02:00"}, timedelta(0))
    assert moved["z"].endswith("Z")
    assert moved["o"].endswith("+02:00")


def test_a_version_number_is_not_mistaken_for_a_timestamp() -> None:
    assert list(timestamps_in({"version": "7.0.14-8"})) == []


def test_the_dataset_lands_on_the_fixed_reference_instant() -> None:
    processed = process(
        capture(),
        book=book(),
        identifiers=REAL,
        captured_at=datetime.fromisoformat("2026-08-07T09:41:00+00:00"),
    )
    assert processed.offset == timedelta(hours=2, minutes=19)


# --- Determinism ------------------------------------------------------------------


def test_two_runs_on_one_capture_produce_identical_output() -> None:
    from tools.mockplane.records import dumps

    first = process(capture(), book=book(), identifiers=REAL)
    second = process(capture(), book=book(), identifiers=REAL)
    assert dumps([record.as_json() for record in first.records]) == dumps(
        [record.as_json() for record in second.records]
    )


def test_the_capture_is_not_mutated_by_being_processed() -> None:
    original = capture()
    process(original, book=book(), identifiers=REAL)
    assert original[0].body["nodes"][0]["root_password"] == "hunter2"


def test_running_the_pipeline_over_its_own_output_changes_nothing() -> None:
    # Re-capturing is meant to be routine, and the committed dataset is built by
    # running an already-pseudonymous set through the same pipeline. Without
    # this the second pass renames a node under one key and not another, and the
    # dataset ends up disagreeing with itself about what a node is called.
    from tools.mockplane.dataset import build

    once = build.processed_for("populated")
    twice = process(
        once.records,
        book=PseudonymBook(key=build.BUILD_KEY.encode(), already_pseudonymous=True),
        identifiers=IdentifierList.empty(),
        captured_at=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )
    from tools.mockplane.records import dumps

    assert dumps([record.as_json() for record in once.records]) == dumps(
        [record.as_json() for record in twice.records]
    )


def test_a_capture_never_passes_a_real_value_through_by_accident() -> None:
    # The pass-through is off by default, and must stay off: a real deployment
    # may genuinely have a node called ``node01``.
    assert PseudonymBook(key=b"k").of(Kind.NODE, "node01") != "node01"
    assert PseudonymBook(key=b"k", already_pseudonymous=True).of(Kind.NODE, "node01") == "node01"
