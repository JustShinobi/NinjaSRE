"""Proves a Grafana credential works, and proves what it is allowed to do.

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
    client_clock_probe,
    client_window_probe,
    refusal_detail,
)
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.grafana.client import GrafanaClient
from integrations.grafana.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for Grafana, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Grafana rejected the credential. Re-issue it: Administration → Users and access → Service accounts → Add service account token"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Grafana credential is configured for this team."
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
    "Administration → Users and access → Service accounts → Add service account token"
)

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "Grafana has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="dashboards:read",
    grants="list dashboards and folders",
    capabilities=("grafana_resource_inventory",),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="annotations:read",
    grants="read the annotation timeline, including deploy markers",
    capabilities=("grafana_recent_changes",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)


_WINDOW_ADVICE: Final = (
    "Grafana answered and holds no dashboards this credential can see. Either nobody has "
    "built any, or this API key is scoped to an organisation or a folder that has none — "
    "check the key's organisation before checking the server."
)


@dataclass(frozen=True, slots=True)
class GrafanaVerifier:
    """Checks a stored Grafana credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /api/health — the cheapest read Grafana offers that still "
            "requires the credential, so it proves authentication without spending quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.list_resources(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                PERMISSION_2,
                build=self._client,
                call=lambda client: client.list_changes(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this Grafana holds something worth opening.

        Grafana stores no time series of its own, so there is no window to ask
        it about; what it holds is dashboards, and a Grafana with none answers
        every question this integration exists to answer with nothing. The
        window is therefore carried and unused, and the description says so —
        a probe that implied a time range it never sent would be a probe whose
        empty result nobody could interpret.
        """

        async def read(client: GrafanaClient, window: DataWindow) -> int:
            # This endpoint takes no time range; the window is carried so every
            # probe in the catalogue has the same signature, and is not faked into
            # a filter the API does not have.
            del window
            answer = await client.list_resources(limit=VERIFY_WINDOW_SAMPLE_LIMIT)
            return len(answer)

        return client_window_probe(
            description=(
                "searches /api/search for dashboards — Grafana holds no time series of its "
                "own, so this asks what it holds rather than what it held recently"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this Grafana thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header Grafana returns on /api/health, which costs no extra "
                "call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Grafana accepted this team's credential."""
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
                detail=refusal_detail(error, _ADVICE),
                status_code=error.status_code,
            )
        return Connectivity(
            reachable=True,
            detail="Grafana accepted the credential.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Grafana said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> GrafanaClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a grafana probe needs a proxy transport and a request context")
        return GrafanaClient(
            transport=transport,
            context=context,
            region=self.region,
            base_url=configured_base_url(self.integration),
        )


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "GrafanaVerifier",
]
