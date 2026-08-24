"""What the deep report says about how this deployment verifies the endpoint.

An operator reading a verification report needs one line answering "and what
was this checked against". Without it, a cluster reached over a pinned
fingerprint and a cluster reached with verification off produce reports that
read identically — and the difference between them is the whole of this
feature.
"""

from __future__ import annotations

import pytest

from gateway.http.deep_verification import trust_line_for
from platform.credentials.proxy.trust import CertificateTrust

pytestmark = pytest.mark.unit

COLONS = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"
PEM = "-----BEGIN CERTIFICATE-----\nMIIBogIBADANBgkq\n-----END CERTIFICATE-----\n"
ADDRESS = "https://pve01.acme.example:8006"


def entry(**trust: object) -> dict[str, object]:
    """Return one active integration entry as the composer reads it."""
    return {"name": "proxmox", "enabled": True, "base_url": ADDRESS, "trust": trust}


def test_a_deployment_that_declared_nothing_says_so_rather_than_saying_nothing() -> None:
    assert trust_line_for("proxmox", [entry()]) == "verifying against the system trust store"


def test_a_pinned_fingerprint_is_reported_as_one() -> None:
    line = trust_line_for("proxmox", [entry(fingerprints=[COLONS])])

    assert "pinned fingerprint" in line
    assert COLONS[:11] in line


def test_a_supplied_certificate_is_reported_as_one() -> None:
    assert "supplied certificate" in trust_line_for("proxmox", [entry(certificate_pem=PEM)])


def test_not_verifying_is_reported_with_who_accepted_it_and_why() -> None:
    """The line an audit review reads first, and the one nobody may have to infer."""
    line = trust_line_for(
        "proxmox",
        [
            entry(
                unverified_reason="lab cluster on a link with no DNS",
                unverified_accepted_by="erik@acme.example",
            )
        ],
    )

    assert "NOT verifying" in line
    assert "erik@acme.example" in line
    assert "no DNS" in line


def test_an_integration_the_document_does_not_name_reports_the_default() -> None:
    assert trust_line_for("grafana", [entry(fingerprints=[COLONS])]) == (
        "verifying against the system trust store"
    )


def test_a_declaration_that_does_not_parse_reports_the_default_rather_than_raising() -> None:
    """A verification report is a diagnostic. It must not fail on a bad document."""
    line = trust_line_for("proxmox", [entry(fingerprints=["probably-a-password"])])

    assert line == "verifying against the system trust store"


def test_the_line_is_the_vocabulary_s_own_rather_than_a_second_wording() -> None:
    """One sentence per form, written once, so two screens cannot disagree."""
    assert trust_line_for("proxmox", [entry(fingerprints=[COLONS])]) == (
        CertificateTrust.pinned(COLONS).describe()
    )


def test_the_line_carries_no_certificate_material() -> None:
    line = trust_line_for("proxmox", [entry(certificate_pem=PEM)])

    assert "BEGIN CERTIFICATE" not in line
    assert "MIIBogIBADANBgkq" not in line
