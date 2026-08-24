"""Whether this deployment trusts the certificate its hypervisor presents.

Homelab Proxmox is self-signed almost without exception — it is the *default
install*, not an eccentricity — and the shortest route to a working integration
is to turn certificate verification off. That is the route this package refuses
to offer, because the management plane of a hypervisor is the last place to
teach an operator that certificate warnings are noise: anything that can
impersonate it can read every guest's configuration and start, stop and
reconfigure all of them.

The four forms, the safe default, and the two things the insecure form may not
be constructed without live one tier down, beside the component that opens the
socket (``platform.credentials.proxy.trust``). Nothing here opens a connection:
every authenticated call crosses the credential proxy, the TLS handshake happens
on its egress, and a trust decision expressed in a client would reach nothing.
So this module is the *declaration* — what Proxmox specifically gets by default,
and which form suits which shape of deployment — and the proxy is the
application.

**Which form to pick, for a hypervisor specifically.**

*Pinned fingerprint* for a single node, and for any cluster reached by IP
address. The pin replaces the identity check rather than adding to it, so it is
the form that works when the certificate names ``pve01`` and the integration is
pointed at ``10.20.20.9``.

*Supplied certificate* for a cluster reached by name. Proxmox mints one
authority per cluster and issues each node a certificate from it, so one paste
covers every node — and chain, expiry and hostname checking all stay on, which
is why it is the stronger of the two where it fits.

*Not verifying* exists, requires a reason and the identity of whoever accepted
it, produces an audit record, and applies only to the addresses the declaration
names. There is no boolean that turns it on.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.trust import (
    CertificateTrust,
    TrustAnchor,
    UnverifiedTransportRefused,
)

#: What a Proxmox integration that configured nothing gets: verification against
#: the system trust store. Named here as well as at the tier that applies it so
#: that a reader of this package sees the default is the safe one rather than
#: having to infer it.
DEFAULT_TRUST: Final = CertificateTrust()

#: Where an operator finds the fingerprint to pin, quoted in a refusal and in
#: the setup document so the two never drift.
FINGERPRINT_IS_SHOWN_AT: Final = "Datacenter → <node> → System → Certificates"


__all__ = [
    "DEFAULT_TRUST",
    "FINGERPRINT_IS_SHOWN_AT",
    "CertificateTrust",
    "TrustAnchor",
    "UnverifiedTransportRefused",
]
