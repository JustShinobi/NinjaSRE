"""Proves a Alertmanager credential works, and proves what it is allowed to do.

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
    refusal_detail,
)
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.alertmanager.client import AlertmanagerClient
from integrations.alertmanager.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for Alertmanager, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Alertmanager rejected the credential. Re-issue it: Your reverse proxy or ingress — Alertmanager ships no authentication of its own"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Alertmanager credential is configured for this team."
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
    "Your reverse proxy or ingress — Alertmanager ships no authentication of its own"
)

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "Alertmanager has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="alerts:read",
    grants="read the alerts Alertmanager is holding",
    capabilities=(
        "alertmanager_incident_statistics",
        "alertmanager_incident_timeline",
    ),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="silences:write",
    grants="create a silence, which is how it acknowledges",
    capabilities=("alertmanager_acknowledge_incident",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)


_WINDOW_ADVICE: Final = (
    "Alertmanager answered and is holding no alerts. For an alert router that is the "
    "healthy state, so this probe proves the query path rather than the data; if you "
    "expected something to be firing, check that Prometheus is reaching this instance."
)


@dataclass(frozen=True, slots=True)
class AlertmanagerVerifier:
    """Checks a stored Alertmanager credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /api/v2/status — the cheapest read Alertmanager offers that still "
            "requires the credential, so it proves authentication without spending quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.list_incidents(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                PERMISSION_2,
                build=self._client,
                call=lambda client: client.incident_timeline(limit=1),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this Alertmanager answers about its alerts.

        Empty is *expected* here, and the reason is worth stating: an alert
        router holding no alerts is an alert router doing its job. What this
        probe establishes is that the query path works and the answer parses —
        the data half of the question has no failing case for this vendor, and
        pretending it does would make the check something an operator learns to
        ignore.

        The read is also not time-bounded, because ``/api/v2/alerts`` answers
        "what is firing now" and has no window to ask for. The window is carried
        and unused rather than faked into a filter the API does not have.
        """

        async def read(client: AlertmanagerClient, window: DataWindow) -> int:
            # This endpoint takes no time range; the window is carried so every
            # probe in the catalogue has the same signature, and is not faked into
            # a filter the API does not have.
            del window
            answer = await client.list_incidents(limit=VERIFY_WINDOW_SAMPLE_LIMIT)
            return len(answer)

        return client_window_probe(
            description=(
                "lists what /api/v2/alerts says is firing right now — this endpoint has no "
                "time range, so the window bounds the report rather than the request"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
            empty_means=EmptyWindow.EXPECTED,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this Alertmanager thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header Alertmanager returns on /api/v2/status, which costs "
                "no extra call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Alertmanager accepted this team's credential."""
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
            # Not "accepted the credential": this vendor ships no
            # authentication and the ordinary configuration sends none, so
            # the sentence would name a credential nobody entered. What was
            # established is that it answered.
            detail="Alertmanager answered.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Alertmanager said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> AlertmanagerClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a alertmanager probe needs a proxy transport and a request context")
        return AlertmanagerClient(
            transport=transport,
            context=context,
            region=self.region,
            base_url=configured_base_url(self.integration),
        )


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "AlertmanagerVerifier",
]
