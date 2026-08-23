"""Proves a SigNoz credential works, and proves what it is allowed to do.

Two questions, and the second is the one that costs an hour when it is skipped.
A credential that authenticates can still be scoped without the permission one
capability needs, and that failure surfaces during an incident as a tool error
with no sign that it was knowable at setup time.

So connectivity is one cheap call, each permission is its own cheap call, and
the report names the permission rather than the failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config.constants.signals import VERIFY_WINDOW_SAMPLE_LIMIT
from integrations._base.access import configured_base_url
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations._verification.diagnostics import (
    ClockSkewProbe,
    DataWindow,
    DataWindowProbe,
    EmptyWindow,
    client_clock_probe,
    client_window_probe,
)
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.signoz.client import SignozClient
from integrations.signoz.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for SigNoz, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "SigNoz rejected the credential. Re-issue it: SigNoz → Settings → API keys"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No SigNoz credential is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call before it left: this host is not in the integration's "
        "declared allow-list."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. Authenticated calls have no path around it."
    ),
}

#: Where an operator changes what this credential may do.
_GRANTED_AT: Final = "SigNoz → Settings → API keys"

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "SigNoz has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="traces:read",
    grants="query the span store",
    capabilities=(
        "signoz_trace_statistics",
        "signoz_slow_traces",
    ),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="version:read",
    grants="read the build version, which the probe uses",
    capabilities=("signoz_trace_statistics",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)


_WINDOW_ADVICE: Final = (
    "SigNoz answered and is holding no spans for this window. On a cluster where nothing "
    "has been instrumented yet that is the ordinary state and not a fault; where something "
    "has, check that its OTLP exporter is pointed at this collector."
)


@dataclass(frozen=True, slots=True)
class SignozVerifier:
    """Checks a stored SigNoz credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /api/v1/version — the cheapest read SigNoz offers that still "
            "requires the credential, so it proves authentication without spending quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.search_traces(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                PERMISSION_2,
                build=self._client,
                call=lambda client: client.slow_traces(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this SigNoz is holding recent spans.

        Empty is *expected* here rather than broken. SigNoz answers "what did it
        call", and a deployment whose containers carry no OTLP instrumentation
        has nothing to call with — reporting that as a fault would train an
        operator to ignore the check on the day it means something.
        """

        async def read(client: SignozClient, window: DataWindow) -> int:
            answer = await client.search_traces(
                start=window.start_epoch_milliseconds,
                end=window.end_epoch_milliseconds,
                limit=VERIFY_WINDOW_SAMPLE_LIMIT,
            )
            return len(answer)

        return client_window_probe(
            description=(
                "queries /api/v3/query_range for spans across the window with no service "
                "filter, in the milliseconds this API indexes in"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
            empty_means=EmptyWindow.EXPECTED,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this SigNoz thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header SigNoz returns on /api/v1/version, which costs no "
                "extra call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether SigNoz accepted this team's credential."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return Connectivity(
                reachable=False,
                detail="the verifier needs a proxy transport and a request context",
            )
        try:
            response = await self._client(transport, context).ping()
        except IntegrationError as error:
            return Connectivity(
                reachable=False,
                detail=_ADVICE.get(error.reason, str(error)),
                status_code=error.status_code,
            )
        return Connectivity(
            reachable=True,
            detail="SigNoz accepted the credential.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what SigNoz said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> SignozClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a signoz probe needs a proxy transport and a request context")
        return SignozClient(
            transport=transport,
            context=context,
            region=self.region,
            base_url=configured_base_url(self.integration),
        )


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "SignozVerifier",
]
