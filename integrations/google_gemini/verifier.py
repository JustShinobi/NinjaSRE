"""Checking that a stored Gemini key actually works, end to end.

An operator who has just stored a provider key wants one question answered:
does it work. The only honest way to answer is to use it — which is why this
makes a real call rather than inspecting the string.

The call is the model listing. It requires the key, spends no inference quota,
and answers the question the operator has next anyway: which models this key may
use.
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
from integrations.google_gemini.client import GeminiClient
from integrations.google_gemini.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

#: What an operator is told for each way the call can fail, in the terms they can
#: act on rather than the transport's.
_ADVICE: Final[dict[IntegrationErrorReason, str]] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Google rejected the key. It has been revoked, it was copied with a character "
        "missing, or it belongs to a project where the Generative Language API is off."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The key is valid and this project has not enabled the Generative Language API, "
        "or billing is not attached to it."
    ),
    IntegrationErrorReason.RATE_LIMITED: (
        "Google is rate-limiting this key. The key is good; the quota is not."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. Authenticated calls have no path around it."
    ),
}

#: Where an operator changes what this credential may do.
_GRANTED_AT: Final = "Google AI Studio, and the API settings of the project the key belongs to"

_NO_INTROSPECTION: Final = (
    "Google publishes no endpoint that reports what a key may do, so the permission is "
    "probed by making the cheapest call that needs it"
)

PERMISSION_1: Final = RequiredPermission(
    name="generativelanguage.models.list",
    grants="list the models this key may use, and call them",
    capabilities=("google_gemini_available_models",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (PERMISSION_1,)


@dataclass(frozen=True, slots=True)
class GeminiVerifier:
    """Checks a stored Gemini credential end to end, and what it may do."""

    integration: str = INTEGRATION

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "lists the models the key may use — the cheapest read that still requires the "
            "credential, so it proves authentication without spending inference quota"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                PERMISSION_1,
                build=self._client,
                call=lambda client: client.ping(),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Google accepted this team's credential."""
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
            detail="Google accepted the key and listed the models it may use.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Google said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> GeminiClient:
        """Return a client for one probe. It holds no credential; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a gemini probe needs a proxy transport and a request context")
        return GeminiClient(transport=transport, context=context)


__all__ = ["PERMISSION_1", "PERMISSIONS", "GeminiVerifier"]
