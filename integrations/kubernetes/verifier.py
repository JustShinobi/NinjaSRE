"""Proves a Kubernetes token works, by reading the API server version.

``/version`` is the right probe because it requires authentication and requires
no RBAC permission beyond it. A probe that listed pods would fail for a token
that is correct but scoped to one namespace, and would tell the operator their
credential was broken when it was their role binding.
"""

from __future__ import annotations

from dataclasses import dataclass

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.kubernetes.client import KubernetesClient
from integrations.kubernetes.config import IN_CLUSTER_HOST, INTEGRATION
from platform.credentials.verification import VerificationResult

_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "The API server rejected the token. Service account tokens expire; mint a fresh "
        "one and rotate it in the vault."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The token authenticated but RBAC denied the read. The credential is fine — the "
        "service account needs a role binding."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Kubernetes token is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call: this API server host is not in the integration's "
        "declared allow-list. Add it with rule_for()."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. Authenticated calls have no path around it."
    ),
}


@dataclass(frozen=True, slots=True)
class KubernetesVerifier:
    """Checks a stored Kubernetes token end to end."""

    integration: str = INTEGRATION
    api_server: str = IN_CLUSTER_HOST

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what the API server said when this team's token was used."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return VerificationResult(
                integration=self.integration,
                ok=False,
                detail="the verifier needs a proxy transport and a request context",
            )

        client = KubernetesClient(transport=transport, context=context, api_server=self.api_server)
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
            detail="The API server accepted the token.",
            status_code=response.status_code,
        )


__all__ = ["KubernetesVerifier"]
