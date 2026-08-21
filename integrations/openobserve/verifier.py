"""Proves a OpenObserve credential works, and proves what it is allowed to do.

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
from integrations.openobserve.client import OpenobserveClient
from integrations.openobserve.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What each failure means for OpenObserve, in the operator's terms. "401" and
#: "403" are different problems with different fixes, and an operator told only
#: that verification failed checks the wrong thing first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "OpenObserve rejected the credential. Re-issue it: OpenObserve → Settings → Users, or the token issued for that user"
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The credential is valid and its scope is not. Check what it is permitted to read "
        "rather than re-issuing it."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No OpenObserve credential is configured for this team."
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
_GRANTED_AT: Final = "OpenObserve → Settings → Users, or the token issued for that user"

#: A vendor that cannot be asked what a credential may do is probed by making the
#: cheapest form of the read the capability itself makes, and the report says so
#: rather than implying an introspection that did not happen.
_NO_INTROSPECTION: Final = (
    "OpenObserve has no permission-introspection endpoint, so each permission is probed "
    "by making the cheapest form of the read that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="streams:read",
    grants="search the streams this user can see",
    capabilities=(
        "openobserve_log_statistics",
        "openobserve_sample_logs",
    ),
    where=_GRANTED_AT,
)
PERMISSION_2: Final = RequiredPermission(
    name="health:read",
    grants="read health, which the connectivity probe uses",
    capabilities=("openobserve_log_statistics",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    PERMISSION_1,
    PERMISSION_2,
)


#: The client's own default when no SQL is given, spelled out so the probe's
#: description and the query it makes cannot drift apart.
_WINDOW_QUERY: Final = "SELECT * FROM logs"

_WINDOW_ADVICE: Final = (
    "OpenObserve answered and is holding no records at all for this window. Nothing is "
    "ingesting into the default stream, or its retention was cut below the window — check "
    "the shippers that write to it before checking anything here."
)


@dataclass(frozen=True, slots=True)
class OpenobserveVerifier:
    """Checks a stored OpenObserve credential end to end, and what it may do."""

    integration: str = INTEGRATION
    region: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "calls /api/default/_health — the cheapest read OpenObserve offers that still "
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
        """Return the read that proves this OpenObserve is holding recent records."""

        async def read(client: OpenobserveClient, window: DataWindow) -> int:
            answer = await client.recent_logs(
                _WINDOW_QUERY,
                start=window.start_epoch_microseconds,
                end=window.end_epoch_microseconds,
                limit=VERIFY_WINDOW_SAMPLE_LIMIT,
            )
            return len(answer)

        return client_window_probe(
            description=(
                f"runs {_WINDOW_QUERY!r} over /api/default/_search for the window, in the "
                f"microseconds this API indexes in — unfiltered, so an empty result means "
                f"the store and not the predicate"
            ),
            build=self._client,
            read=read,
            advice=_WINDOW_ADVICE,
        )

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this OpenObserve thinks it is."""
        return client_clock_probe(
            description=(
                "reads the Date header OpenObserve returns on /api/default/_health, which "
                "costs no extra call and is the server's own clock rather than a proxy's"
            ),
            build=self._client,
            call=lambda client: client.ping(),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether OpenObserve accepted this team's credential."""
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
            detail="OpenObserve accepted the credential.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what OpenObserve said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> OpenobserveClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a openobserve probe needs a proxy transport and a request context")
        return OpenobserveClient(transport=transport, context=context, region=self.region)


__all__ = [
    "PERMISSION_1",
    "PERMISSION_2",
    "PERMISSIONS",
    "OpenobserveVerifier",
]
