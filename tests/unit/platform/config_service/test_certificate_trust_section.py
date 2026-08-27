"""What an operator may declare about an address's certificate, in the document.

The section is closed like every other, so the interesting assertions are the
refusals: a boolean that turns verification off is not ignored, it does not
validate; a private key pasted where the certificate goes is refused by name;
and the insecure form cannot exist without the two things an audit record needs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform.config_service.schema.integrations import IntegrationsConfig
from platform.config_service.schema.root import RootConfig
from platform.credentials.proxy.trust import TrustAnchor

pytestmark = pytest.mark.unit

COLONS = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"
OTHER = "FF:" + COLONS[3:]
PEM = "-----BEGIN CERTIFICATE-----\nMIIBogIBADANBgkq\n-----END CERTIFICATE-----\n"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIBogIBADANBgkq\n-----END PRIVATE KEY-----\n"


def entry(**trust: object) -> IntegrationsConfig:
    """Return the integrations section with one Proxmox entry carrying ``trust``."""
    return IntegrationsConfig.model_validate(
        {
            "active": [
                {
                    "name": "proxmox",
                    "base_url": "https://pve01.acme.example:8006",
                    "trust": trust,
                }
            ]
        }
    )


def only(config: IntegrationsConfig):
    """Return the single entry as the declaration the proxy would apply."""
    found = config.for_name("proxmox")
    assert found is not None
    return found.certificate_trust()


# -- the four forms, and the one that costs nothing ------------------------------


def test_an_entry_that_declares_nothing_verifies_against_the_system_store() -> None:
    config = IntegrationsConfig.model_validate({"active": [{"name": "proxmox"}]})

    assert only(config).anchor is TrustAnchor.SYSTEM_TRUST_STORE


def test_a_fingerprint_declared_is_the_pinned_form() -> None:
    assert only(entry(fingerprints=[COLONS])).anchor is TrustAnchor.PINNED_FINGERPRINT


def test_a_certificate_declared_is_the_supplied_form() -> None:
    assert only(entry(certificate_pem=PEM)).anchor is TrustAnchor.SUPPLIED_CERTIFICATE


def test_a_reason_and_an_identity_together_are_the_unverified_form() -> None:
    declared = only(
        entry(
            unverified_reason="lab cluster on a link with no DNS",
            unverified_accepted_by="erik@acme.example",
        )
    )

    assert declared.anchor is TrustAnchor.UNVERIFIED


# -- the refusals ------------------------------------------------------------------


def test_unverified_without_a_reason_is_refused_naming_the_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        entry(unverified_accepted_by="erik@acme.example")


def test_unverified_without_an_identity_is_refused_naming_the_identity() -> None:
    with pytest.raises(ValidationError, match="accepted"):
        entry(unverified_reason="lab cluster on a link with no DNS")


def test_a_private_key_where_the_certificate_goes_is_refused_by_name() -> None:
    with pytest.raises(ValidationError, match="private key"):
        entry(certificate_pem=PRIVATE_KEY)


def test_a_value_that_is_not_a_certificate_is_refused() -> None:
    with pytest.raises(ValidationError, match="BEGIN CERTIFICATE"):
        entry(certificate_pem="pve01.acme.example")


def test_a_fingerprint_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValidationError, match="SHA-256 fingerprint"):
        entry(fingerprints=["probably-a-password"])


def test_declaring_multiple_trust_modes_is_refused() -> None:
    """An entry may declare at most one trust mode, not a combination."""
    with pytest.raises(ValidationError, match="only one trust mode"):
        entry(
            fingerprints=[COLONS],
            certificate_pem=PEM,
        )

    with pytest.raises(ValidationError, match="only one trust mode"):
        entry(
            fingerprints=[COLONS],
            unverified_reason="testing",
            unverified_accepted_by="operator@example.com",
        )

    with pytest.raises(ValidationError, match="only one trust mode"):
        entry(
            certificate_pem=PEM,
            unverified_reason="testing",
            unverified_accepted_by="operator@example.com",
        )


@pytest.mark.parametrize(
    "field",
    ["verify", "insecure", "skip_tls_verify", "verify_ssl", "unverified", "tls_insecure"],
)
def test_no_boolean_turns_verification_off_and_writing_one_is_refused(field: str) -> None:
    """The section is closed, so a switch is refused rather than stored and ignored.

    Stored and ignored is worse than refused: the operator sees the value they
    typed in the document, believes it took effect, and the behaviour they
    expected never happens.
    """
    with pytest.raises(ValidationError):
        entry(**{field: True})


def test_no_field_of_the_section_is_a_boolean_at_all() -> None:
    from platform.config_service.schema.integrations import CertificateTrustSettings

    booleans = [
        name
        for name, declared in CertificateTrustSettings.model_fields.items()
        if declared.annotation is bool
    ]

    assert not booleans


# -- both spellings, a set, and the addresses it names -----------------------------


def test_a_fingerprint_without_separators_is_accepted() -> None:
    declared = only(entry(fingerprints=[COLONS.replace(":", "")]))

    assert declared.matches_fingerprint(COLONS)


def test_a_cluster_declares_one_fingerprint_per_node_in_one_entry() -> None:
    declared = only(entry(fingerprints=[COLONS, OTHER]))

    assert declared.matches_fingerprint(COLONS)
    assert declared.matches_fingerprint(OTHER)


def test_the_declaration_names_the_address_the_entry_is_pointed_at() -> None:
    declared = only(entry(fingerprints=[COLONS]))

    assert declared.addresses == ("pve01.acme.example",)


def test_an_entry_with_no_address_declares_trust_for_nothing() -> None:
    config = IntegrationsConfig.model_validate(
        {"active": [{"name": "proxmox", "trust": {"fingerprints": [COLONS]}}]}
    )

    assert only(config).addresses == ()


# -- and the whole document still parses -------------------------------------------


def test_the_section_reaches_the_document_root() -> None:
    config = RootConfig.of(
        {
            "integrations": {
                "active": [
                    {
                        "name": "proxmox",
                        "base_url": "https://pve01.acme.example:8006",
                        "trust": {"fingerprints": [COLONS]},
                    }
                ]
            }
        }
    )
    found = config.integrations.for_name("proxmox")

    assert found is not None
    assert found.certificate_trust().anchor is TrustAnchor.PINNED_FINGERPRINT


# -- what the document's own secret scan makes of certificate material -------------


def _validator():
    """Return the validator a write path uses, with this deployment's guardrails."""
    from platform.config_service.validation import ConfigValidator
    from platform.guardrails.engine import GuardrailEngine

    return ConfigValidator(guardrails=GuardrailEngine())


def test_a_public_certificate_is_not_a_secret_and_is_not_refused_as_one() -> None:
    """A certificate is the public half. It may live in the tree, as an address does."""
    found = _validator().secret_shaped(
        {"integrations": {"active": [{"name": "proxmox", "trust": {"certificate_pem": PEM}}]}}
    )

    assert found == ()


def test_a_private_key_anywhere_in_the_document_is_refused_as_a_secret() -> None:
    """The second line, behind the field's own refusal.

    The field refuses a private key because it knows what a certificate looks
    like. This refuses one wherever it was pasted, including a field that has no
    opinion about its shape — the case the field-level check cannot cover.
    """
    found = _validator().secret_shaped(
        {"integrations": {"active": [{"name": "proxmox", "settings": {"note": PRIVATE_KEY}}]}}
    )

    assert found
    assert found[0][0] == "integrations.active.0.settings.note"
