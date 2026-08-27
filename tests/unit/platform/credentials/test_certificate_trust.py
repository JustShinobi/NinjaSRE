"""The vocabulary of certificate trust, at the tier that applies it.

The declaration lives beside the proxy because the proxy is what opens the
socket. These tests fix the four forms, the safe default, and the two things
the insecure form may never be constructed without.
"""

from __future__ import annotations

import pytest

from platform.credentials.proxy.trust import (
    DEFAULT_TRUST,
    CertificateTrust,
    TrustAnchor,
    TrustRegistry,
    UnverifiedTransportRefused,
)

pytestmark = pytest.mark.unit

#: A real SHA-256 fingerprint shape: 32 colon-separated hex pairs, the way a
#: management interface renders the one an operator copies.
COLONS = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"
#: The same value as ``openssl`` prints it, which is what makes rejecting it
#: pedantry rather than validation.
BARE = COLONS.replace(":", "")
OTHER = "FF:" + COLONS[3:]

PEM = "-----BEGIN CERTIFICATE-----\nMIIBogIBADANBgkq\n-----END CERTIFICATE-----\n"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIBogIBADANBgkq\n-----END PRIVATE KEY-----\n"
RSA_PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBADAN\n-----END RSA PRIVATE KEY-----\n"


# --- The four forms, and which one costs nothing -------------------------------


def test_the_default_form_is_the_system_trust_store_and_it_verifies() -> None:
    assert DEFAULT_TRUST.anchor is TrustAnchor.SYSTEM_TRUST_STORE
    assert DEFAULT_TRUST.verifies
    assert CertificateTrust().anchor is TrustAnchor.SYSTEM_TRUST_STORE


def test_a_pinned_fingerprint_is_its_own_form_and_still_verifies() -> None:
    trust = CertificateTrust.pinned(COLONS)

    assert trust.anchor is TrustAnchor.PINNED_FINGERPRINT
    assert trust.verifies
    assert trust.is_pinned


def test_a_supplied_certificate_is_its_own_form_and_still_verifies() -> None:
    trust = CertificateTrust.with_certificate(PEM)

    assert trust.anchor is TrustAnchor.SUPPLIED_CERTIFICATE
    assert trust.verifies


def test_unverified_is_the_fourth_form_and_the_only_one_that_does_not() -> None:
    trust = CertificateTrust.unverified(reason="lab link with no DNS", accepted_by="erik@acme")

    assert trust.anchor is TrustAnchor.UNVERIFIED
    assert not trust.verifies


def test_there_are_exactly_four_forms() -> None:
    assert len(TrustAnchor) == 4


# --- The insecure form cannot be constructed carelessly ------------------------


def test_unverified_without_a_reason_names_the_reason_as_what_is_missing() -> None:
    with pytest.raises(UnverifiedTransportRefused, match="reason"):
        CertificateTrust.unverified(reason="   ", accepted_by="erik@acme")


def test_unverified_without_an_identity_names_the_identity_as_what_is_missing() -> None:
    with pytest.raises(UnverifiedTransportRefused, match="who accepted"):
        CertificateTrust.unverified(reason="lab link with no DNS", accepted_by="  ")


def test_the_flag_alone_is_refused_so_there_is_no_boolean_route_to_not_verifying() -> None:
    with pytest.raises(UnverifiedTransportRefused):
        CertificateTrust(verify=False)


# --- The certificate field holds a certificate and nothing else ----------------


def test_a_value_with_no_certificate_header_is_refused() -> None:
    with pytest.raises(ValueError, match="BEGIN CERTIFICATE"):
        CertificateTrust.with_certificate("pve01.acme.example")


@pytest.mark.parametrize("pasted", [PRIVATE_KEY, RSA_PRIVATE_KEY])
def test_a_private_key_is_refused_by_name_rather_than_as_a_shape_problem(pasted: str) -> None:
    with pytest.raises(ValueError, match="private key"):
        CertificateTrust.with_certificate(pasted)


def test_a_refused_certificate_never_becomes_a_stored_value() -> None:
    with pytest.raises(ValueError):
        CertificateTrust(certificate_pem=PRIVATE_KEY)


# --- Fingerprints: two spellings, and a set rather than a value ----------------


@pytest.mark.parametrize("spelling", [COLONS, BARE, COLONS.lower()])
def test_both_spellings_a_tool_produces_are_accepted(spelling: str) -> None:
    assert CertificateTrust.pinned(spelling).matches_fingerprint(BARE)


def test_a_value_that_is_not_a_fingerprint_is_refused() -> None:
    with pytest.raises(ValueError, match="SHA-256 fingerprint"):
        CertificateTrust.pinned("probably-a-password")


def test_a_cluster_declares_one_fingerprint_per_node_in_one_declaration() -> None:
    trust = CertificateTrust.pinned(COLONS, OTHER)

    assert trust.matches_fingerprint(COLONS)
    assert trust.matches_fingerprint(OTHER)
    assert len(trust.fingerprints) == 2


def test_a_fingerprint_outside_the_declared_set_does_not_match() -> None:
    assert not CertificateTrust.pinned(COLONS).matches_fingerprint(OTHER)


def test_the_same_fingerprint_declared_twice_is_one_member_of_the_set() -> None:
    assert len(CertificateTrust.pinned(COLONS, COLONS.lower()).fingerprints) == 1


# --- The addresses a declaration is made for -----------------------------------


def test_a_declaration_records_the_addresses_it_was_made_for() -> None:
    trust = CertificateTrust.pinned(COLONS).for_addresses("pve01.acme.example", "10.20.20.9")

    assert trust.addresses == ("10.20.20.9", "pve01.acme.example")


def test_an_address_is_matched_without_its_scheme_or_port() -> None:
    trust = CertificateTrust.pinned(COLONS).for_addresses("https://pve01.acme.example:8006")

    assert trust.addresses == ("pve01.acme.example",)


def test_a_registry_answers_with_the_declaration_made_for_that_address() -> None:
    pinned = CertificateTrust.pinned(COLONS).for_addresses("pve01.acme.example")
    registry = TrustRegistry([pinned])

    assert registry.for_host("pve01.acme.example") is pinned


def test_an_address_no_declaration_names_gets_the_safe_default() -> None:
    registry = TrustRegistry([CertificateTrust.pinned(COLONS).for_addresses("pve01.acme.example")])

    assert registry.for_host("pve02.acme.example").anchor is TrustAnchor.SYSTEM_TRUST_STORE


def test_replacing_the_declarations_rebuilds_rather_than_accumulates() -> None:
    registry = TrustRegistry([CertificateTrust.pinned(COLONS).for_addresses("pve01.acme.example")])

    registry.replace_all(())

    assert registry.for_host("pve01.acme.example").anchor is TrustAnchor.SYSTEM_TRUST_STORE


def test_replacing_the_declarations_moves_the_generation_on() -> None:
    registry = TrustRegistry(())
    before = registry.generation

    registry.replace_all([CertificateTrust.pinned(COLONS).for_addresses("pve01.acme.example")])

    assert registry.generation != before


# --- What a report reads back, and what an audit line may carry ----------------


def test_each_form_describes_itself_in_one_line() -> None:
    assert DEFAULT_TRUST.describe() == "verifying against the system trust store"
    assert COLONS[:11] in CertificateTrust.pinned(COLONS).describe()
    assert "supplied certificate" in CertificateTrust.with_certificate(PEM).describe()
    unverified = CertificateTrust.unverified(reason="lab link", accepted_by="erik@acme")
    assert "NOT verifying" in unverified.describe()
    assert "erik@acme" in unverified.describe()


def test_the_audit_record_names_the_form_the_addresses_and_who_accepted() -> None:
    trust = CertificateTrust.unverified(
        reason="lab cluster reachable only over a link with no DNS",
        accepted_by="erik@acme.example",
    ).for_addresses("pve01.acme.example")
    record = trust.audit_record()

    assert record["anchor"] == TrustAnchor.UNVERIFIED.value
    assert record["accepted_by"] == "erik@acme.example"
    assert record["reason"]
    assert record["addresses"] == ["pve01.acme.example"]


def test_the_audit_record_carries_the_fingerprints_because_they_are_not_secret() -> None:
    record = CertificateTrust.pinned(COLONS, OTHER).audit_record()

    assert sorted(record["fingerprints"]) == sorted([COLONS, OTHER])


def test_no_certificate_material_reaches_the_audit_record_or_the_description() -> None:
    trust = CertificateTrust.with_certificate(PEM).for_addresses("pve01.acme.example")

    assert "BEGIN CERTIFICATE" not in repr(trust.audit_record())
    assert "BEGIN CERTIFICATE" not in trust.describe()
    assert "MIIBogIBADANBgkq" not in repr(trust.audit_record())
