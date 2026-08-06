"""Proves a Datadog credential works, by using it (FR-021).

One cheap authenticated call and a translation of what came back into the
sentence an operator needs. The translation is the value: "401" and "403" are
different problems with different fixes, and an operator told only that
verification failed will check the wrong thing first.
"""

from __future__ import annotations

from dataclasses import dataclass

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.datadog.client import DatadogClient
from integrations.datadog.config import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for Datadog specifically, in the operator's terms.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Datadog rejected the API key. Re-issue it in Organisation Settings → API Keys."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The API key is valid but the application key does not carry the scopes this "
        "needs. Check the application key's scopes rather than the API key."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Datadog credential is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call before it left. Either Datadog declares no injection "
        "rule in this deployment, or the configured site is not one of its declared hosts."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. Authenticated calls have no path around it."
    ),
}


@dataclass(frozen=True, slots=True)
class DatadogVerifier:
    """Checks a stored Datadog credential end to end."""

    integration: str = INTEGRATION
    site: str = "datadoghq.com"

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Datadog said when this team's credential was used."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return VerificationResult(
                integration=self.integration,
                ok=False,
                detail="the verifier needs a proxy transport and a request context",
            )

        client = DatadogClient(transport=transport, context=context, site=self.site)
        try:
            response = await client.ping()
        except IntegrationError as error:
            return VerificationResult(
                integration=self.integration,
                ok=False,
                detail=_ADVICE.get(error.reason, str(error)),
                status_code=error.status_code,
            )
        return VerificationResult(
            integration=self.integration,
            ok=True,
            detail="Datadog accepted both keys.",
            status_code=response.status_code,
        )


__all__ = ["DatadogVerifier"]
