"""HMAC signature verification: PagerDuty, Sentry, and the generic signed webhook."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HmacVerifier:
    """Verifies a body's signature against a shared secret.

    Compared with ``hmac.compare_digest``, always — a signature check whose
    comparison takes signature-dependent time is a signature check an
    attacker can time their way past one byte at a time.
    """

    secret: str
    header: str
    prefix: str = ""
    digest: str = "sha256"

    def verify(self, *, headers: Mapping[str, str], body: bytes) -> bool:
        """Return whether ``body`` was signed with this verifier's secret."""
        presented = headers.get(self.header, "")
        if self.prefix:
            if not presented.startswith(self.prefix):
                return False
            presented = presented[len(self.prefix) :]
        if not presented:
            return False
        try:
            digestmod = getattr(hashlib, self.digest)
        except AttributeError:
            return False
        expected = hmac.new(self.secret.encode("utf-8"), body, digestmod).hexdigest()
        return hmac.compare_digest(expected, presented.strip().lower())


__all__ = ["HmacVerifier"]
