"""Proves a Datadog credential works, and proves what it is allowed to do.

Two questions, and the second is the one that costs an hour when it is skipped.
Datadog issues two keys with different meanings: the API key identifies the
organisation and the *application* key carries the scopes. An operator who
pasted both correctly can still have an application key issued without
``logs_read_data``, and everything about that configuration looks right — the
connection works, the monitors list, and the log capabilities fail during an
incident with a 403 that reads like a network problem.

So connectivity is one cheap call and each permission is its own cheap call, and
the report names the scope rather than the failure (FR-009, FR-010). The
translation is the value throughout: "401" and "403" are different problems with
different fixes, and an operator told only that verification failed will check
the wrong thing first.

**Datadog cannot be asked what a key is allowed to do.** There is no scope
introspection endpoint, so each probe is the cheapest read the capability itself
makes, and each says so (FR-011). The consequence is honest rather than hidden:
a probe answered with a 403 proves the scope is missing, and one answered with a
200 proves it is present for that read — which is exactly what the capability
needs it for.
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
from integrations.datadog.client import DatadogClient
from integrations.datadog.schema import INTEGRATION
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

#: Where an operator goes to change what an application key may do. Written once
#: because it belongs in every message about a missing scope.
_SCOPES_PAGE: Final = "Organisation Settings → Application Keys, on the key this deployment uses"

LOGS_READ: Final = RequiredPermission(
    name="logs_read_data",
    grants="read log events and their aggregations",
    capabilities=("datadog_log_statistics", "datadog_sample_logs"),
    where=_SCOPES_PAGE,
)

MONITORS_READ: Final = RequiredPermission(
    name="monitors_read",
    grants="list monitors and their alerting state",
    capabilities=("datadog_log_statistics",),
    where=_SCOPES_PAGE,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (LOGS_READ, MONITORS_READ)

#: FR-011, written down. Datadog exposes no way to ask what a key may do, so
#: each permission is probed by making the cheapest form of the read that needs
#: it, and the report says so rather than implying an introspection that did not
#: happen.
_NO_INTROSPECTION: Final = (
    "Datadog has no scope-introspection endpoint, so each permission is probed by making "
    "the cheapest form of the read that needs it"
)

#: The window a probe reads. One minute, because a probe is about whether the
#: call is permitted and not about what is in the answer.
_PROBE_START: Final = "now-1m"
_PROBE_END: Final = "now"


@dataclass(frozen=True, slots=True)
class DatadogVerifier:
    """Checks a stored Datadog credential end to end, and what it may do."""

    integration: str = INTEGRATION
    site: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "lists one monitor — the cheapest call that requires both the API key and the "
            "application key, which is exactly what a credential check needs"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per scope this integration's capabilities need."""
        return (
            client_probe(
                LOGS_READ,
                build=self._client,
                call=lambda client: client.aggregate_logs(
                    "*", start=_PROBE_START, end=_PROBE_END, limit=1
                ),
                fallback_note=_NO_INTROSPECTION,
            ),
            client_probe(
                MONITORS_READ,
                build=self._client,
                call=lambda client: client.alerting_monitors(),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Datadog accepted this team's credential."""
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
            detail="Datadog accepted both keys.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Datadog said when this team's credential was used.

        The connectivity-only answer, which is what the credential surfaces ask
        for. The permission half is reached through the verification runner —
        the CLI's check command and the CI gate both go that way.
        """
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> DatadogClient:
        """Return a client for one probe. It holds no key; see ``_base/client.py``."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a Datadog probe needs a proxy transport and a request context")
        return DatadogClient(transport=transport, context=context, site=self.site)


__all__ = [
    "LOGS_READ",
    "MONITORS_READ",
    "PERMISSIONS",
    "DatadogVerifier",
]
