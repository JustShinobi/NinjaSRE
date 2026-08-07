"""mTLS verification: trusts the reverse proxy's client-certificate verdict.

NinjaSRE does not terminate TLS itself in a standard deployment; an ingress or
reverse proxy does, and negotiates the client certificate. This verifier reads
the two headers every major ingress sets after a successful handshake —
nginx's ``ssl_client_verify``/``ssl_client_s_dn`` and their equivalents —
rather than parsing a certificate itself, which is a proxy's job and not this
process's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

VERIFIED = "SUCCESS"


@dataclass(frozen=True, slots=True)
class MutualTlsVerifier:
    """Verifies the proxy reports a successful handshake for the expected subject."""

    expected_subject: str
    verify_header: str = "X-SSL-Client-Verify"
    subject_header: str = "X-SSL-Client-Subject"

    def verify(self, *, headers: Mapping[str, str], body: bytes) -> bool:  # noqa: ARG002 — WebhookVerifier's shape
        """Return whether the proxy reports a verified client certificate matching the expected subject."""
        if headers.get(self.verify_header, "") != VERIFIED:
            return False
        return headers.get(self.subject_header, "") == self.expected_subject


__all__ = ["MutualTlsVerifier"]
