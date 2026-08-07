"""Shared-secret verification: Alertmanager, Datadog, Grafana, and Opsgenie."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SharedSecretVerifier:
    """Verifies a token presented in a header matches the configured secret."""

    secret: str
    header: str
    prefix: str = "Bearer "

    def verify(self, *, headers: Mapping[str, str], body: bytes) -> bool:  # noqa: ARG002 — WebhookVerifier's shape
        """Return whether the presented token matches this verifier's secret."""
        presented = headers.get(self.header, "")
        if self.prefix and presented.startswith(self.prefix):
            presented = presented[len(self.prefix) :]
        if not presented:
            return False
        return hmac.compare_digest(presented, self.secret)


__all__ = ["SharedSecretVerifier"]
