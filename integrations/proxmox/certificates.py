"""Whether this deployment trusts the certificate its hypervisor presents.

Homelab Proxmox is self-signed almost without exception, and the shortest route
to a working integration is to turn certificate verification off. That is the
route this module exists to make harder than the two alternatives, because the
management plane of a hypervisor is the last place to teach an operator that
certificate warnings are noise: anything that can impersonate it can read every
guest's configuration and start, stop and reconfigure all of them.

So there are three states and only one of them is the default:

**Verifying against the system trust store.** What a deployment with a real
certificate — an internal CA, an ACME issuance — gets, and it needs no
configuration at all.

**Verifying against a supplied certificate or a pinned fingerprint.** What a
self-signed deployment gets. The operator copies the node's certificate, or its
SHA-256 fingerprint, out of the Proxmox web interface once. Verification stays
on; what changes is *which* certificate satisfies it, which is strictly stronger
than the system store for a host that issues its own.

**Not verifying.** Reachable only through ``unverified``, which requires a reason
and the identity of whoever accepted it, and which produces an audit record.
There is no boolean anywhere that turns this on, and constructing the value with
``verify=False`` directly raises — a flag would be flipped at 03:00 during an
outage and never flipped back.

**Where the trust is applied.** Nothing here opens a socket. The TLS handshake
happens on the far side of the credential proxy, which is the only component
that talks to a vendor, so this is the *declaration* the proxy's egress is
configured from and the thing a verification report reads back to an operator.
Keeping the declaration here rather than in the proxy is what lets a
Proxmox-specific default — verification on, pinning offered — be stated once
beside the integration it belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

#: A SHA-256 fingerprint as the Proxmox web interface renders it: 32 hex pairs
#: separated by colons. Accepted without the separators too, because copying it
#: out of ``openssl`` gives that form and rejecting it would be pedantry.
_FINGERPRINT = re.compile(r"^(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f]{64}$")

#: What a certificate a deployment supplied has to start with for this to be a
#: certificate at all. A private key pasted here would be a private key in the
#: configuration store, so the prefix is checked rather than assumed.
_PEM_PREFIX: Final = "-----BEGIN CERTIFICATE-----"


class UnverifiedTransportRefused(ValueError):
    """Certificate verification was disabled without the explicit, audited setting.

    Raised rather than warned. A warning about an unverified management plane is
    a line in a log nobody reads, and the whole difficulty here is that the
    insecure option is also the convenient one.
    """


@dataclass(frozen=True, slots=True)
class CertificateTrust:
    """What this deployment will accept from a Proxmox endpoint.

    Immutable, and the only route to ``verify=False`` is ``unverified``, which
    demands the two things an audit record needs: why, and who decided.
    """

    verify: bool = True
    #: The PEM the operator copied out of the node, when the certificate is
    #: self-signed and they chose to supply it rather than pin it.
    certificate_pem: str = ""
    #: The SHA-256 fingerprint they pinned instead. One or the other; pinning is
    #: shorter to copy and the web interface shows it directly.
    fingerprint_sha256: str = ""
    #: Why verification is off, when it is. Empty in every other state.
    reason: str = ""
    #: Who accepted the risk. An audit record with no name in it records that
    #: somebody did something.
    accepted_by: str = ""

    def __post_init__(self) -> None:
        if not self.verify and not (self.reason.strip() and self.accepted_by.strip()):
            raise UnverifiedTransportRefused(
                "certificate verification for Proxmox may only be disabled through "
                "CertificateTrust.unverified(reason=..., accepted_by=...). Supplying the "
                "node's certificate or pinning its fingerprint is barely harder and keeps "
                "the management plane authenticated."
            )
        if self.certificate_pem and not self.certificate_pem.lstrip().startswith(_PEM_PREFIX):
            raise ValueError(
                f"a supplied Proxmox certificate must begin with {_PEM_PREFIX!r}. A private "
                f"key pasted here would be a private key in the configuration store."
            )
        if self.fingerprint_sha256 and _FINGERPRINT.match(self.fingerprint_sha256) is None:
            raise ValueError(
                "a pinned Proxmox certificate is identified by its SHA-256 fingerprint — "
                "32 colon-separated hex pairs, as the web interface shows it, or the same "
                "64 characters without separators"
            )

    @property
    def verifies(self) -> bool:
        """Return whether the endpoint's certificate is checked at all."""
        return self.verify

    @property
    def is_pinned(self) -> bool:
        """Return whether trust rests on one certificate rather than on a store."""
        return bool(self.certificate_pem or self.fingerprint_sha256)

    @classmethod
    def with_certificate(cls, pem: str) -> CertificateTrust:
        """Return trust anchored on the certificate the operator supplied."""
        return cls(certificate_pem=pem)

    @classmethod
    def pinned(cls, fingerprint: str) -> CertificateTrust:
        """Return trust anchored on one certificate's SHA-256 fingerprint."""
        return cls(fingerprint_sha256=fingerprint.strip())

    @classmethod
    def unverified(cls, *, reason: str, accepted_by: str) -> CertificateTrust:
        """Return the explicitly accepted, audited, unverified setting.

        Both arguments are required and neither may be blank, which is the whole
        mechanism: an operator who cannot say why they turned it off has not
        decided to turn it off, they have skipped a step.
        """
        return cls(verify=False, reason=reason.strip(), accepted_by=accepted_by.strip())

    def describe(self) -> str:
        """Return the one line a verification report shows an operator."""
        if not self.verify:
            return (
                f"NOT verifying the endpoint certificate — accepted by {self.accepted_by} "
                f"because {self.reason}"
            )
        if self.fingerprint_sha256:
            shown = self.fingerprint_sha256[:11]
            return f"verifying against the pinned fingerprint {shown}…"
        if self.certificate_pem:
            return "verifying against the supplied certificate"
        return "verifying against the system trust store"

    def audit_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record of this decision.

        Carries no certificate material: a PEM in an audit trail is bulk that
        proves nothing the fingerprint does not, and a fingerprint is what an
        operator compares against the node.
        """
        return {
            "verify": self.verify,
            "anchor": (
                "pinned-fingerprint"
                if self.fingerprint_sha256
                else "supplied-certificate"
                if self.certificate_pem
                else "system-trust-store"
            ),
            "fingerprint": self.fingerprint_sha256,
            "reason": self.reason,
            "accepted_by": self.accepted_by,
        }


#: What a deployment that configured nothing gets. Named so that a reader can
#: see that the default is the safe one rather than having to infer it.
DEFAULT_TRUST: Final = CertificateTrust()


__all__ = ["DEFAULT_TRUST", "CertificateTrust", "UnverifiedTransportRefused"]
