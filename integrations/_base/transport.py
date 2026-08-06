"""How a client reaches the proxy, in-process or over a socket.

FR-011 asks for the proxy to run in-process in the ``dev`` profile and as a
separate service otherwise, with identical behaviour. The way to get identical
behaviour is not discipline — it is to have one implementation, and to make the
difference a transport rather than a code path.

``InProcessProxyTransport`` drives the ASGI application directly, in the same
event loop, with no socket. ``HttpProxyTransport`` sends the same envelope to
the same application over HTTP. Both encode with ``encode_forward_request`` and
decode with ``decode_forward_response``, both get their errors from the same
status-to-reason mapping, and a test drives one stack through each and asserts
the results match.

**The HTTP transport uses the standard library.** NinjaSRE's runtime dependency
list is six packages and the operator has to audit every one of them, so adding
an HTTP client for this is a real cost. ``urllib.request`` in a worker thread is
what the standard library offers, and the concurrency it costs is bounded by the
same semaphore the loop already puts on parallel tool calls. A deployment that
outgrows it substitutes its own ``ProxyTransport`` — which is why this is a
protocol.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urljoin

from config.constants.security import (
    CAPABILITY_CONTEXT_HEADER,
    CREDENTIAL_PROXY_TIMEOUT_SECONDS,
    INTEGRATION_CONTEXT_HEADER,
    PROXY_FORWARD_PATH,
    TEAM_CONTEXT_HEADER,
    TENANT_CONTEXT_HEADER,
)
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from platform.credentials.proxy.app import (
    ProxyApp,
    decode_forward_response,
    encode_forward_request,
)
from platform.credentials.proxy.errors import error_from_record
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

#: The header the standalone proxy authenticates its callers with. The value is
#: the deployment's own shared secret between agent and proxy, not a vendor
#: credential — it grants the ability to *ask* for injection, never to read
#: anything.
PROXY_AUTHORIZATION_HEADER = "Authorization"


@runtime_checkable
class ProxyTransport(Protocol):
    """Carries one forward request to the proxy and brings the answer back."""

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Return the vendor's answer to ``request``.

        Raises ``IntegrationError`` for anything that stopped the call —
        including a proxy refusal, which arrives classified rather than as a
        status the caller has to interpret.
        """


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is making this call. Every field is safe in a trace.

    This is the whole of what a capability knows about credentials: which
    organisation, which team, and which capability is asking. The proxy turns
    that into a secret; the capability never learns it did.
    """

    org_id: str
    team_id: str
    capability: str

    def headers(self, integration: str) -> dict[str, str]:
        """Return the context headers, for a transport that carries them separately."""
        return {
            TENANT_CONTEXT_HEADER: self.org_id,
            TEAM_CONTEXT_HEADER: self.team_id,
            CAPABILITY_CONTEXT_HEADER: self.capability,
            INTEGRATION_CONTEXT_HEADER: integration,
        }


class InProcessProxyTransport:
    """Drives the proxy's ASGI application directly, with no socket.

    The ``dev`` profile's mount (FR-011). Same application object, same engine,
    same code — the only thing missing is the loopback hop, which is why a
    mandatory proxy costs a developer nothing.
    """

    __slots__ = ("_app",)

    def __init__(self, app: ProxyApp) -> None:
        self._app = app

    @property
    def app(self) -> ProxyApp:
        """Return the application this transport drives."""
        return self._app

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Return the vendor's answer to ``request``."""
        status, payload = await self._call(request)
        return _interpret(request, status, payload)

    async def _call(self, request: ProxyRequest) -> tuple[int, bytes]:
        """Run one ASGI request-response cycle against the application."""
        body = encode_forward_request(request)
        scope: dict[str, Any] = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": PROXY_FORWARD_PATH,
            "raw_path": PROXY_FORWARD_PATH.encode("ascii"),
            "query_string": b"",
            "headers": [
                (name.lower().encode("ascii"), value.encode("utf-8"))
                for name, value in request.headers.items()
            ],
        }

        sent: list[bytes] = []
        status = 500
        delivered = False

        async def receive() -> MutableMapping[str, Any]:
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: MutableMapping[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            elif message["type"] == "http.response.body":
                sent.append(bytes(message.get("body", b"")))

        await self._app(scope, receive, send)
        return status, b"".join(sent)


@dataclass(frozen=True, slots=True)
class HttpProxyTransport:
    """Sends the same envelope to a proxy running as its own service.

    The ``standard`` and ``enterprise`` profiles. ``token`` is the deployment's
    shared secret for the agent-to-proxy hop, supplied by composition — never
    read by a client, and never a vendor credential.
    """

    base_url: str
    token: str = ""
    timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Return the vendor's answer to ``request``."""
        status, payload = await asyncio.to_thread(self._post, request)
        return _interpret(request, status, payload)

    def _post(self, request: ProxyRequest) -> tuple[int, bytes]:
        """Send one envelope over HTTP. Runs in a worker thread."""
        headers = {"content-type": "application/json"}
        if self.token:
            headers[PROXY_AUTHORIZATION_HEADER] = f"Bearer {self.token}"

        outbound = urllib.request.Request(  # noqa: S310 — the URL is the operator's own proxy
            urljoin(self.base_url, PROXY_FORWARD_PATH),
            data=encode_forward_request(request),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 — same
                outbound, timeout=self.timeout_seconds
            ) as answer:
                return int(answer.status), answer.read()
        except urllib.error.HTTPError as error:
            # A refusal is a status the proxy meant to send, so it is read
            # rather than raised: the body carries the classified reason.
            return int(error.code), error.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise IntegrationError(
                f"the credential proxy at {self.base_url!r} did not answer: "
                f"{type(error).__name__}. Authenticated calls have no path that "
                f"does not go through it.",
                integration=request.integration,
                reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
            ) from error


def _interpret(request: ProxyRequest, status: int, payload: bytes) -> OutboundResponse:
    """Return the vendor response, or raise the classified refusal it carries."""
    if status == 200:
        return decode_forward_response(payload)

    try:
        record = json.loads(payload)
    except json.JSONDecodeError:
        raise IntegrationError(
            f"the credential proxy answered {status} for {request.integration!r} with "
            f"a body that is not a proxy error record",
            integration=request.integration,
            reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
            status_code=status,
        ) from None

    raise IntegrationError.from_proxy(error_from_record(record))


__all__ = [
    "PROXY_AUTHORIZATION_HEADER",
    "HttpProxyTransport",
    "InProcessProxyTransport",
    "ProxyTransport",
    "RequestContext",
]
