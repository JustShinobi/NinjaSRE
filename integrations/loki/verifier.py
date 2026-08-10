"""Proves a Loki credential works, and proves what it is allowed to do.

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
from integrations.loki.client import LokiClient
from integrations.loki.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for Loki, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Loki rejected the credential. Re-issue it: Grafana Cloud → Access Policies, or whatever your gateway issues for a self-hosted install"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Loki credential is configured for this team."
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
_GRANTED_AT: Final = (
    "Grafana Cloud → Access Policies, or whatever your gateway issues for a self-hosted install"
)

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "Loki has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="logs:read",
    grants="run LogQL queries against the tenant's streams",
    capabilities=(
        "loki_log_statistics",
        "loki_sample_logs",
    ),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="labels:read",
    grants="list label names and values, which the probe uses",
    capabilities=("loki_log_statistics",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)


#: Any stream at all. A selector naming a job would report "no logs" for a
#: deployment that simply does not run that job, which is the opposite of what
#: this probe is for.
_WINDOW_QUERY: Final = '{job=~".+"}'

_WINDOW_ADVICE: Final = (
    "Loki answered and is holding no lines at all for this window. Nothing is shipping to "
    "it, its retention was cut below the window, or this credential reads a tenant nobody "
    "writes to — check the agents that push to it before checking anything here."
)


@dataclass(frozen=True, slots=True)
class LokiVerifier:
    """Checks a stored Loki credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /loki/api/v1/labels — the cheapest read Loki offers that still "
            "requires the credential, so it proves authentication without spending quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.search_logs(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                PERMISSION_2,
                build=self._client,
                call=lambda client: client.recent_logs(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this Loki is holding recent lines."""

        async def read(client: LokiClient, window: DataWindow) -> int:
            answer = await client.recent_logs(
                _WINDOW_QUERY,
                start=window.start_epoch_nanoseconds,
                end=window.end_epoch_nanoseconds,
                limit=VERIFY_WINDOW_SAMPLE_LIMIT,
            )
            return len(answer)

        return client_window_probe(
            description=(
                f"queries {_WINDOW_QUERY!r} over /loki/api/v1/query_range for the window — "
                f"any stream at all, so an empty result means the store and not the selector"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this Loki thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header Loki returns on /loki/api/v1/labels, which costs no "
                "extra call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Loki accepted this team's credential."""
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
            detail="Loki accepted the credential.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Loki said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> LokiClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a loki probe needs a proxy transport and a request context")
        return LokiClient(transport=transport, context=context, region=self.region)


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "LokiVerifier",
]
