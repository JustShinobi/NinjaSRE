"""Proves an AWS credential works — and that the proxy signed for it.

A signed request that AWS accepts proves three things at once: the key is valid,
the proxy's SigV4 implementation agrees with AWS's, and the clocks are close
enough. When it fails, telling those apart is the whole job, because
``SignatureDoesNotMatch`` and ``InvalidClientTokenId`` send an operator to
completely different places.

The permission half is where AWS differs from most vendors and where the effort
pays. An IAM policy is written per action, so a credential that reaches
CloudWatch at all can still be missing exactly one of the two actions this
integration uses — and the symptom is one capability failing during an incident
while the other works, which reads as a bug in the platform rather than as a
policy gap. Each action gets its own probe, and a denial names the action
(FR-009, FR-010).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.aws.client import CloudWatchLogsClient
from integrations.aws.schema import DEFAULT_REGION, INTEGRATION
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


#: Where an operator changes what this credential may do.
_POLICY: Final = "the IAM policy attached to this access key or the role it assumes"

DESCRIBE_LOG_GROUPS: Final = RequiredPermission(
    name="logs:DescribeLogGroups",
    grants="list the log groups in this account and region",
    capabilities=("aws_list_log_groups",),
    where=_POLICY,
)

FILTER_LOG_EVENTS: Final = RequiredPermission(
    name="logs:FilterLogEvents",
    grants="read log events from a log group over a time window",
    capabilities=("aws_filter_log_events",),
    where=_POLICY,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (DESCRIBE_LOG_GROUPS, FILTER_LOG_EVENTS)

#: FR-011. ``iam:SimulatePrincipalPolicy`` would answer this properly, and
#: requiring it would mean asking every operator for a *wider* permission than
#: the integration needs in order to check the narrow ones — which is the wrong
#: trade. So each action is probed by performing it, as cheaply as it can be
#: performed, and the report says so.
_NO_SIMULATION: Final = (
    "AWS can only report a permission through iam:SimulatePrincipalPolicy, which is a "
    "wider grant than this integration needs, so each action is probed by performing it "
    "on the smallest possible request"
)

#: A log group name no account has. ``FilterLogEvents`` against it is refused
#: with ``AccessDenied`` when the action is not permitted and with
#: ``ResourceNotFound`` when it is — which is exactly the distinction the probe
#: needs, and it reads nothing.
_ABSENT_LOG_GROUP: Final = "/ninjasre/permission-probe"


@dataclass(frozen=True, slots=True)
class AwsVerifier:
    """Checks a stored AWS credential by making one proxy-signed call."""

    integration: str = INTEGRATION
    region: str = DEFAULT_REGION

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "asks CloudWatch Logs for one log group — the cheapest signed call there is, "
            "and one whose success proves the key, the proxy's signature, and the clock "
            "all at once"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per IAM action this integration's capabilities need."""
        return (
            client_probe(
                DESCRIBE_LOG_GROUPS,
                build=self._client,
                call=lambda client: client.describe_log_groups(),
                fallback_note=_NO_SIMULATION,
            ),
            client_probe(
                FILTER_LOG_EVENTS,
                build=self._client,
                call=lambda client: client.filter_log_events(
                    _ABSENT_LOG_GROUP, start_ms=0, end_ms=1, limit=1, max_pages=1
                ),
                fallback_note=_NO_SIMULATION,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether AWS accepted a request the proxy signed for this team."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return Connectivity(
                reachable=False,
                detail="the verifier needs a proxy transport and a request context",
            )
        try:
            response = await self._client(transport, context).ping()
        except IntegrationError as error:
            return Connectivity(
                reachable=False, detail=_explain(error), status_code=error.status_code
            )
        return Connectivity(
            reachable=True,
            detail="AWS accepted a request the proxy signed.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what AWS said when this team's credential was signed and used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> CloudWatchLogsClient:
        """Return a client for one probe. It holds no signing key; the proxy signs."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("an AWS probe needs a proxy transport and a request context")
        return CloudWatchLogsClient(transport=transport, context=context, region=self.region)


def _explain(error: IntegrationError) -> str:
    """Return the sentence that sends an operator to the right place."""
    for code, advice in _BODY_ADVICE:
        if code in error.detail:
            return advice
    return _REASON_ADVICE.get(error.reason, str(error))


__all__ = [
    "DESCRIBE_LOG_GROUPS",
    "FILTER_LOG_EVENTS",
    "PERMISSIONS",
    "AwsVerifier",
]
