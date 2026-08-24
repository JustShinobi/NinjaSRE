"""What the panel says when the refusal was about a certificate.

The defect: a self-signed cluster — the default install — was reported as
"Neither the credential proxy nor any configured Proxmox node answered", which
sends an operator to check a network that is fine. They check it, find it
correct, and conclude the product is broken.

So the verdict has to carry the refusal that actually happened, fingerprint and
all, and the sentence for a genuinely silent host has to stay exactly where it
was.
"""

from __future__ import annotations

import pytest

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import RequestContext
from integrations.proxmox.verifier import ProxmoxVerifier
from platform.credentials.proxy.errors import (
    CertificateNameMismatch,
    CertificatePinBroken,
    CertificateUntrusted,
    UpstreamUnreachable,
)
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

HOST = "10.20.20.9"
OBSERVED = "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
EXPECTED = "11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00"

#: The sentence a silent host produces, and the one no certificate refusal may
#: ever be reported as.
SILENT_HOST = "Neither the credential proxy nor any configured Proxmox node answered"


class _Refusing:
    """A proxy transport that refuses every call the way the real one would."""

    def __init__(self, refusal: Exception) -> None:
        self._refusal = refusal

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        del request
        raise self._refusal


async def _verdict(refusal: Exception) -> str:
    """Return the sentence the panel shows for ``refusal``."""
    transport = _Refusing(IntegrationError.from_proxy(refusal))
    context = RequestContext(org_id="acme", team_id="", capability="integration.verify")
    connectivity = await ProxmoxVerifier().connect(transport, context)
    assert not connectivity.reachable
    return connectivity.detail


# -- the three certificate refusals reach the operator as themselves -------------


async def test_an_untrusted_certificate_is_reported_as_one_and_names_it() -> None:
    shown = await _verdict(CertificateUntrusted("proxmox", host=HOST, observed=OBSERVED))

    assert OBSERVED in shown
    assert SILENT_HOST not in shown


async def test_a_broken_pin_shows_both_fingerprints() -> None:
    shown = await _verdict(
        CertificatePinBroken("proxmox", host=HOST, expected=(EXPECTED,), observed=OBSERVED)
    )

    assert EXPECTED in shown
    assert OBSERVED in shown
    assert SILENT_HOST not in shown


async def test_a_name_that_does_not_match_shows_the_address_and_the_certificate() -> None:
    shown = await _verdict(
        CertificateNameMismatch("proxmox", host=HOST, certificate_names=("pve02.lan.example",))
    )

    assert HOST in shown
    assert "pve02.lan.example" in shown
    assert SILENT_HOST not in shown


async def test_the_verdict_says_where_this_vendor_shows_the_fingerprint() -> None:
    """The Proxmox-specific half: comparing it needs knowing where to look."""
    shown = await _verdict(CertificateUntrusted("proxmox", host=HOST, observed=OBSERVED))

    assert "Certificates" in shown


# -- and a silent host still says what it always said -----------------------------


async def test_a_silent_host_is_still_reported_as_a_silent_host() -> None:
    shown = await _verdict(UpstreamUnreachable("proxmox", host=HOST, cause="TimeoutError: "))

    assert SILENT_HOST in shown
    assert "certificate" not in shown.lower()
    assert "fingerprint" not in shown.lower()


async def test_the_certificate_verdict_and_the_silent_host_verdict_are_not_the_same() -> None:
    refused = await _verdict(CertificateUntrusted("proxmox", host=HOST, observed=OBSERVED))
    silent = await _verdict(UpstreamUnreachable("proxmox", host=HOST, cause="TimeoutError: "))

    assert refused != silent


def test_the_message_table_has_an_arm_for_the_certificate_reason() -> None:
    """Keyed on the reason, so a refusal cannot fall through to another vendor's advice."""
    from integrations.proxmox.verifier import _ADVICE

    assert IntegrationErrorReason.CERTIFICATE_UNTRUSTED in _ADVICE


async def test_no_verdict_carries_certificate_material() -> None:
    for refusal in (
        CertificateUntrusted("proxmox", host=HOST, observed=OBSERVED),
        CertificatePinBroken("proxmox", host=HOST, expected=(EXPECTED,), observed=OBSERVED),
        CertificateNameMismatch("proxmox", host=HOST, certificate_names=("pve02.lan.example",)),
    ):
        shown = await _verdict(refusal)
        assert "BEGIN CERTIFICATE" not in shown
        assert "PRIVATE KEY" not in shown
