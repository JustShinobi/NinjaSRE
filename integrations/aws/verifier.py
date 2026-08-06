"""Proves an AWS credential works — and that the proxy signed for it.

A signed request that AWS accepts proves three things at once: the key is valid,
the proxy's SigV4 implementation agrees with AWS's, and the clocks are close
enough. When it fails, telling those apart is the whole job, because
``SignatureDoesNotMatch`` and ``InvalidClientTokenId`` send an operator to
completely different places.
"""

from __future__ import annotations

from dataclasses import dataclass

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.aws.client import CloudWatchLogsClient
from integrations.aws.config import DEFAULT_REGION, INTEGRATION
from platform.credentials.verification import VerificationResult

#: AWS puts the useful part in an error code inside the body, and the status
#: alone does not distinguish "wrong key" from "wrong signature". Both arrive as
#: 403, so the body is what is matched.
_BODY_ADVICE: tuple[tuple[str, str], ...] = (
    (
        "SignatureDoesNotMatch",
        "The key is recognised but the signature did not verify. That is the proxy's "
        "signing or a clock more than fifteen minutes out, not a wrong credential.",
    ),
    (
        "InvalidClientTokenId",
        "AWS does not recognise this access key id. It has been deleted or belongs to a "
        "different account.",
    ),
    (
        "ExpiredToken",
        "The session token has expired. Rotate the credential, or configure a refresher "
        "so the proxy renews it before expiry.",
    ),
    (
        "AccessDenied",
        "The credential is valid and its IAM policy does not permit this read. Fix the "
        "policy rather than the key.",
    ),
)

_REASON_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No AWS credential is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call: this regional endpoint is not in the integration's "
        "declared allow-list. Add the service and region with rule_for()."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. The signing key lives there, so there is "
        "no path around it."
    ),
}


@dataclass(frozen=True, slots=True)
class AwsVerifier:
    """Checks a stored AWS credential by making one proxy-signed call."""

    integration: str = INTEGRATION
    region: str = DEFAULT_REGION

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what AWS said when this team's credential was signed and used."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return VerificationResult(
                integration=self.integration,
                ok=False,
                detail="the verifier needs a proxy transport and a request context",
            )

        client = CloudWatchLogsClient(transport=transport, context=context, region=self.region)
        try:
            response = await client.ping()
        except IntegrationError as error:
            return VerificationResult(
                integration=self.integration,
                ok=False,
                detail=_explain(error),
                status_code=error.status_code,
            )
        return VerificationResult(
            integration=self.integration,
            ok=True,
            detail="AWS accepted a request the proxy signed.",
            status_code=response.status_code,
        )


def _explain(error: IntegrationError) -> str:
    """Return the sentence that sends an operator to the right place."""
    for code, advice in _BODY_ADVICE:
        if code in error.detail:
            return advice
    return _REASON_ADVICE.get(error.reason, str(error))


__all__ = ["AwsVerifier"]
