"""Proves a Prometheus credential works, and proves what it is allowed to do.

Two questions, and the second is the one that costs an hour when it is skipped.
A credential that authenticates can still be scoped without the permission one
capability needs, and that failure surfaces during an incident as a tool error
with no sign that it was knowable at setup time.

So connectivity is one cheap call, each permission is its own cheap call, and
the report names the permission rather than the failure.

A third question, and for a metric store it is the one that matters most: a
Prometheus whose scrape targets are all down answers 200 to everything above and
holds nothing. An investigation that reaches it concludes the metric never moved,
with a citation. So verification also evaluates a query over a recent window and
reports an empty result as its own state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config.constants.signals import VERIFY_WINDOW_SAMPLE_LIMIT
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations._verification.diagnostics import (
    ClockSkewProbe,
    DataWindow,
    DataWindowProbe,
    client_clock_probe,
    client_window_probe,
)
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.prometheus.client import PrometheusClient
from integrations.prometheus.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for Prometheus, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Prometheus rejected the credential. Re-issue it: Your reverse proxy, ingress, or Grafana Cloud access policy — Prometheus itself ships no authentication"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Prometheus credential is configured for this team."
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
_GRANTED_AT: Final = "Your reverse proxy, ingress, or Grafana Cloud access policy — Prometheus itself ships no authentication"

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "Prometheus has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="query",
    grants="evaluate PromQL over the stored series",
    capabilities=("prometheus_metric_statistics",),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="rules:read",
    grants="read alerting rules and their current state",
    capabilities=("prometheus_active_alerts",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)

#: The one query every Prometheus with a single scrape target answers, and the
#: only query that is empty exactly when the server has nothing. Anything more
#: specific would report "no data" for a deployment that simply does not run the
#: exporter the query named.
_WINDOW_QUERY: Final = "up"

_WINDOW_ADVICE: Final = (
    "Prometheus answered and is holding no series at all for this window. Its scrape "
    "targets are down, its retention was cut below the window, or this credential reads "
    "a tenant nobody writes to — check /targets on the server before checking anything here."
)


@dataclass(frozen=True, slots=True)
class PrometheusVerifier:
    """Checks a stored Prometheus credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /api/v1/status/buildinfo — the cheapest read Prometheus offers that still "
            "requires the credential, so it proves authentication without spending quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.query_metric(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                PERMISSION_2,
                build=self._client,
                call=lambda client: client.list_alerts(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this Prometheus is holding recent series."""

        async def read(client: PrometheusClient, window: DataWindow) -> int:
            answer = await client.query_metric(
                _WINDOW_QUERY,
                start=window.start_rfc3339,
                end=window.end_rfc3339,
                limit=VERIFY_WINDOW_SAMPLE_LIMIT,
            )
            return len(answer)

        return client_window_probe(
            description=(
                f"evaluates {_WINDOW_QUERY!r} over /api/v1/query_range for the window — the "
                f"one query a server with any scrape target at all answers, so an empty "
                f"result means the server and not the query"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this Prometheus thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header Prometheus returns on /api/v1/status/buildinfo, which "
                "costs no extra call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Prometheus accepted this team's credential."""
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
            detail="Prometheus accepted the credential.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Prometheus said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> PrometheusClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a prometheus probe needs a proxy transport and a request context")
        return PrometheusClient(transport=transport, context=context, region=self.region)


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "PrometheusVerifier",
]
