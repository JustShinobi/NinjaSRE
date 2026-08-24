"""What this deployment accepts from an address it is pointed at.

An appliance that mints its own certificate — a hypervisor management plane, a
self-hosted metrics store, an ingress in front of either — is the ordinary case,
not an eccentricity, and the shortest route to a working integration is to turn
certificate verification off. That is the route this module exists to make
harder than the three alternatives, because a management plane is the last place
to teach an operator that certificate warnings are noise: anything that can
impersonate it can read everything behind it and change most of it.

So there are four forms and only one of them is the default:

**The system trust store.** What a deployment with a publicly issued or
internally chained certificate gets, and it needs no configuration at all.

**A pinned fingerprint.** The operator copies the node's SHA-256 fingerprint out
of its own interface once. Verification stays on; what changes is that one
certificate satisfies it instead of a store, which is strictly stronger than the
system store for a host that issues its own. The field is a *set*, because a
cluster presents one certificate per node.

**A supplied certificate.** The authority the cluster minted for itself, pasted
once. It becomes the trust anchor, and chain building, expiry and hostname
checking all stay on — which is why an authority covers a whole cluster and a
fingerprint covers one node.

**Not verifying.** Reachable only through :meth:`CertificateTrust.unverified`,
which requires a reason and the identity of whoever accepted it, and which
produces an audit record. There is no boolean anywhere that turns this on, and
constructing the value with ``verify=False`` directly raises — a flag would be
flipped at 03:00 during an outage and never flipped back.

**Where the declaration lives, and where it is applied.** Nothing here opens a
socket. The TLS handshake happens on the far side of the credential proxy, which
is the only component that talks to a vendor, so this is the vocabulary the
proxy's egress is configured from. It lives beside the proxy rather than beside
a vendor package for the same reason an injection rule does: the component that
applies the decision cannot import the package that declares it, so the type
descends and the declaration stays where the vendor is described.

**Trust is scoped to an address, never to a vendor.** ``addresses`` is what a
declaration covers, and :class:`TrustRegistry` is the lookup. A vendor-wide
acceptance would silently cover an address added months later by somebody else —
the same failure the periodically rebuilt egress allow-list exists to avoid, and
it would be incoherent for the looser rule to live in the same document.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

#: What a certificate a deployment supplied has to start with for this to be a
#: certificate at all.
CERTIFICATE_PEM_HEADER: Final = "-----BEGIN CERTIFICATE-----"

#: What a private key's own header ends with, whatever algorithm precedes it —
#: ``PRIVATE KEY``, ``RSA PRIVATE KEY``, ``EC PRIVATE KEY``. Matched as a
#: suffix so a new key type does not quietly become an accepted paste.
_PRIVATE_KEY_MARKER: Final = "PRIVATE KEY-----"

#: A SHA-256 fingerprint as a management interface renders it: 32 hex pairs
#: separated by colons. Accepted without the separators too, because copying it
#: out of ``openssl`` gives that form and refusing it would be pedantry.
_FINGERPRINT = re.compile(r"^(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f]{64}$")


class TrustAnchor(StrEnum):
    """What a connection to an address is verified against.

    Closed, and read as a value in an audit line. An open set would make "how
    was this deployment verifying when the call went out" a question with no
    answer six months later.
    """

    SYSTEM_TRUST_STORE = "system-trust-store"
    PINNED_FINGERPRINT = "pinned-fingerprint"
    SUPPLIED_CERTIFICATE = "supplied-certificate"
    UNVERIFIED = "unverified"


class UnverifiedTransportRefused(ValueError):
    """Certificate verification was disabled without the explicit, audited setting.

    Raised rather than warned. A warning about an unverified management plane is
    a line in a log nobody reads, and the whole difficulty here is that the
    insecure option is also the convenient one.
    """


def host_of(address: str) -> str:
    """Return the bare host an address names, without scheme, port or path.

    An operator types a URL and a certificate is presented by a host, so the two
    are reconciled once, here, rather than at each place that compares them.
    """
    trimmed = address.strip()
    if not trimmed:
        return ""
    authority = trimmed.split("://", 1)[-1].split("/", 1)[0]
    if authority.startswith("["):
        # An IPv6 literal is bracketed, and its colons are not a port separator.
        return authority.partition("]")[0].lstrip("[").lower()
    return authority.split(":", 1)[0].lower()


def normalise_fingerprint(value: str) -> str:
    """Return ``value`` in the one spelling comparisons are made in.

    Uppercase hex with no separators. Both spellings a tool produces are
    accepted on the way in and neither is what a comparison should have to know
    about, so the canonical form exists and is never what an operator sees.
    """
    return value.replace(":", "").strip().upper()


@dataclass(frozen=True, slots=True)
class CertificateTrust:
    """What this deployment will accept from the addresses it names.

    Immutable, and the only route to ``verify=False`` is
    :meth:`unverified`, which demands the two things an audit record needs:
    why, and who decided.
    """

    verify: bool = True
    #: The authority or leaf certificate the operator supplied, when they chose
    #: to supply one rather than pin. Public material: it may live in the
    #: configuration tree the way an address does.
    certificate_pem: str = ""
    #: The SHA-256 fingerprints they pinned instead, as they wrote them. A set,
    #: because a cluster presents one certificate per node and declaring three
    #: is one decision rather than three.
    fingerprints: tuple[str, ...] = ()
    #: Why verification is off, when it is. Empty in every other form.
    reason: str = ""
    #: Who accepted the risk. An audit record with no name in it records that
    #: somebody did something.
    accepted_by: str = ""
    #: The addresses this declaration was made for, as bare hosts. Empty means
    #: the declaration names nothing and therefore covers nothing — a registry
    #: built from it answers with the default everywhere.
    addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.verify:
            missing = [
                name
                for name, value in (
                    ("a reason", self.reason),
                    ("who accepted it", self.accepted_by),
                )
                if not value.strip()
            ]
            if missing:
                raise UnverifiedTransportRefused(
                    f"accepting an unverified certificate needs {' and '.join(missing)}. "
                    f"Use CertificateTrust.unverified(reason=..., accepted_by=...). Pinning "
                    f"the node's fingerprint or supplying its authority is barely harder and "
                    f"keeps the endpoint authenticated."
                )
        if self.certificate_pem:
            pasted = self.certificate_pem.lstrip()
            if _PRIVATE_KEY_MARKER in pasted:
                raise ValueError(
                    "that is a private key, not a certificate. A private key pasted here "
                    "would be a private key in the configuration store; the certificate is "
                    "the public half and is the half that is needed."
                )
            if not pasted.startswith(CERTIFICATE_PEM_HEADER):
                raise ValueError(
                    f"a supplied certificate must begin with {CERTIFICATE_PEM_HEADER!r}"
                )
        for fingerprint in self.fingerprints:
            if _FINGERPRINT.match(fingerprint) is None:
                raise ValueError(
                    "a pinned certificate is identified by its SHA-256 fingerprint — 32 "
                    "colon-separated hex pairs, as a management interface shows it, or the "
                    "same 64 characters without separators"
                )

    # -- what form this is ----------------------------------------------------

    @property
    def anchor(self) -> TrustAnchor:
        """Return which of the four forms this declaration is."""
        if not self.verify:
            return TrustAnchor.UNVERIFIED
        if self.fingerprints:
            return TrustAnchor.PINNED_FINGERPRINT
        if self.certificate_pem:
            return TrustAnchor.SUPPLIED_CERTIFICATE
        return TrustAnchor.SYSTEM_TRUST_STORE

    @property
    def verifies(self) -> bool:
        """Return whether the endpoint's certificate is checked at all."""
        return self.verify

    @property
    def is_pinned(self) -> bool:
        """Return whether trust rests on declared material rather than on a store."""
        return bool(self.certificate_pem or self.fingerprints)

    def matches_fingerprint(self, digest: str) -> bool:
        """Return whether ``digest`` is one of the fingerprints declared.

        Membership of a set rather than equality with a value, which is what
        makes two nodes sharing a wildcard certificate an ordinary case instead
        of a special one.
        """
        wanted = normalise_fingerprint(digest)
        return any(normalise_fingerprint(known) == wanted for known in self.fingerprints)

    def covers(self, address: str) -> bool:
        """Return whether this declaration was made for ``address``."""
        return host_of(address) in self.addresses

    # -- construction ---------------------------------------------------------

    @classmethod
    def with_certificate(cls, pem: str) -> CertificateTrust:
        """Return trust anchored on the certificate the operator supplied."""
        return cls(certificate_pem=pem)

    @classmethod
    def pinned(cls, *fingerprints: str) -> CertificateTrust:
        """Return trust anchored on one or more certificates' SHA-256 fingerprints."""
        declared = tuple(value.strip() for value in fingerprints if value.strip())
        seen: dict[str, str] = {}
        for value in declared:
            seen.setdefault(normalise_fingerprint(value), value)
        return cls(fingerprints=tuple(seen.values()))

    @classmethod
    def unverified(cls, *, reason: str, accepted_by: str) -> CertificateTrust:
        """Return the explicitly accepted, audited, unverified setting.

        Both arguments are required and neither may be blank, which is the whole
        mechanism: an operator who cannot say why they turned it off has not
        decided to turn it off, they have skipped a step.
        """
        return cls(verify=False, reason=reason.strip(), accepted_by=accepted_by.strip())

    def for_addresses(self, *addresses: str) -> CertificateTrust:
        """Return this declaration, scoped to the addresses it was made for."""
        hosts = {host_of(address) for address in addresses}
        hosts.discard("")
        return CertificateTrust(
            verify=self.verify,
            certificate_pem=self.certificate_pem,
            fingerprints=self.fingerprints,
            reason=self.reason,
            accepted_by=self.accepted_by,
            addresses=tuple(sorted(hosts)),
        )

    # -- what is read back ----------------------------------------------------

    def describe(self) -> str:
        """Return the one line a verification report shows an operator."""
        if not self.verify:
            return (
                f"NOT verifying the endpoint certificate — accepted by {self.accepted_by} "
                f"because {self.reason}"
            )
        if self.fingerprints:
            shown = ", ".join(f"{value[:11]}…" for value in self.fingerprints)
            return f"verifying against the pinned fingerprint {shown}"
        if self.certificate_pem:
            return "verifying against the supplied certificate"
        return "verifying against the system trust store"

    def audit_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record of this decision.

        Carries no certificate material: a PEM in an audit trail is bulk that
        proves nothing the fingerprint does not, and a fingerprint is what an
        operator compares against what the node shows them.
        """
        return {
            "anchor": self.anchor.value,
            "verify": self.verify,
            "fingerprints": list(self.fingerprints),
            "addresses": list(self.addresses),
            "reason": self.reason,
            "accepted_by": self.accepted_by,
        }


#: What a deployment that configured nothing gets. Named so a reader can see
#: that the default is the safe one rather than having to infer it.
DEFAULT_TRUST: Final = CertificateTrust()


class TrustRegistry:
    """Which declaration governs each address, for the component that applies it.

    Mutable in exactly one way — :meth:`replace_all` — because the proxy rebuilds
    what it enforces from the configuration tree on a cycle, and a registry that
    could only be widened cannot express a declaration an operator removed. The
    generation counter exists so a component caching something derived from a
    declaration can tell that its cache is stale without comparing declarations.
    """

    __slots__ = ("_by_host", "_generation")

    def __init__(self, declarations: Iterable[CertificateTrust] = ()) -> None:
        self._by_host: Mapping[str, CertificateTrust] = {}
        self._generation = 0
        self.replace_all(declarations)

    @property
    def generation(self) -> int:
        """Return a counter that changes whenever the declarations are rebuilt."""
        return self._generation

    def replace_all(self, declarations: Iterable[CertificateTrust]) -> None:
        """Rebuild the registry from ``declarations``, discarding what it held.

        Rebuild rather than accumulate. A declaration an operator deleted has to
        stop applying at the next cycle; a registry that only ever added would
        keep enforcing a decision nobody holds any more, which is precisely the
        shape of failure that makes a trust decision worth scoping to an address.
        """
        rebuilt: dict[str, CertificateTrust] = {}
        for declaration in declarations:
            for host in declaration.addresses:
                rebuilt[host] = declaration
        self._by_host = rebuilt
        self._generation += 1

    def for_host(self, host: str) -> CertificateTrust:
        """Return the declaration made for ``host``, or the safe default."""
        return self._by_host.get(host_of(host), DEFAULT_TRUST)

    def hosts(self) -> tuple[str, ...]:
        """Return every address a declaration was made for."""
        return tuple(sorted(self._by_host))

    def declarations(self) -> tuple[CertificateTrust, ...]:
        """Return the distinct declarations this registry holds."""
        seen: list[CertificateTrust] = []
        for declaration in self._by_host.values():
            if declaration not in seen:
                seen.append(declaration)
        return tuple(seen)


__all__ = [
    "CERTIFICATE_PEM_HEADER",
    "DEFAULT_TRUST",
    "CertificateTrust",
    "TrustAnchor",
    "TrustRegistry",
    "UnverifiedTransportRefused",
    "host_of",
    "normalise_fingerprint",
]
