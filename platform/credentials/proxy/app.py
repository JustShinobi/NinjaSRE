"""The proxy's internal API, as a plain ASGI application.

Two paths and no framework. ``/internal/forward`` takes an envelope describing
the call a capability wants to make and returns the vendor's answer;
``/internal/health`` says whether the proxy is ready and what it can
authenticate. There is deliberately no third path, and in particular no path
that returns a credential: FR-010 says no configuration may enable a bypass, and
the cheapest way to keep that true is for the bypass not to exist as a route.

**Why hand-written ASGI.** The application is thirty lines of protocol and a
call into ``ProxyEngine``. A framework would add a dependency to a tree the
operator has to audit, in exchange for routing between two paths. It is also
what makes FR-011 straightforward: an ASGI callable is mountable in-process by
the ``dev`` profile *and* servable by any ASGI server in ``standard``, with one
implementation, so "identical behaviour" is a fact rather than a promise about
two codebases.

**The wire format is explicit, not HTTP-transparent.** The envelope carries the
method, URL, headers, and a base64 body rather than reusing the request line and
headers of the request that carried it. Encoding by hand costs a few lines and
buys two things: the body survives being binary without anything guessing at a
charset, and the tenant, team, integration, and capability arrive as named
fields rather than as headers a middlebox might strip.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from config.constants.security import PROXY_FORWARD_PATH, PROXY_HEALTH_PATH
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.errors import (
    MalformedProxyRequest,
    ProxyError,
    ProxyErrorReason,
)
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

#: What each proxy reason becomes on the wire. Chosen so that a caller reading
#: only the status still takes the right action: 4xx is "fix your side", 429 is
#: "slow down", 502 is "the vendor did not answer".
STATUS_FOR_REASON: Mapping[ProxyErrorReason, int] = {
    ProxyErrorReason.MALFORMED_REQUEST: 400,
    ProxyErrorReason.UNKNOWN_INTEGRATION: 404,
    ProxyErrorReason.EGRESS_DENIED: 403,
    ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED: 412,
    ProxyErrorReason.CREDENTIAL_UNREADABLE: 500,
    ProxyErrorReason.CREDENTIAL_EXPIRED: 412,
    ProxyErrorReason.REFRESH_FAILED: 502,
    ProxyErrorReason.RATE_LIMITED: 429,
    ProxyErrorReason.UPSTREAM_UNREACHABLE: 502,
}


def encode_forward_request(request: ProxyRequest) -> bytes:
    """Return the envelope a client sends to ``/internal/forward``.

    The body is base64 because JSON has no bytes. It is not encryption and is
    not meant to look like any: the envelope carries no secret, which is the
    entire reason a client is allowed to build one.
    """
    return json.dumps(
        {
            "integration": request.integration,
            "org_id": request.org_id,
            "team_id": request.team_id,
            "capability": request.capability,
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "body": None if request.body is None else base64.b64encode(request.body).decode(),
        }
    ).encode("utf-8")


def decode_forward_request(payload: bytes) -> ProxyRequest:
    """Return the request an envelope describes, or raise ``MalformedProxyRequest``."""
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise MalformedProxyRequest(
            f"the forward envelope is not valid JSON: {error.msg}", integration=""
        ) from error
    if not isinstance(document, dict):
        raise MalformedProxyRequest("the forward envelope must be a JSON object", integration="")

    encoded = document.get("body")
    try:
        return ProxyRequest(
            integration=str(document.get("integration", "")),
            org_id=str(document.get("org_id", "")),
            team_id=str(document.get("team_id", "")),
            capability=str(document.get("capability", "")),
            method=str(document.get("method", "")),
            url=str(document.get("url", "")),
            headers={str(k): str(v) for k, v in dict(document.get("headers", {})).items()},
            body=None if encoded is None else base64.b64decode(str(encoded)),
        )
    except ValueError as error:
        raise MalformedProxyRequest(
            f"the forward envelope is incomplete: {error}",
            integration=str(document.get("integration", "")),
        ) from error


def encode_forward_response(response: OutboundResponse) -> bytes:
    """Return the envelope the proxy answers a forwarded call with."""
    return json.dumps(
        {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": base64.b64encode(response.body).decode(),
        }
    ).encode("utf-8")


def decode_forward_response(payload: bytes) -> OutboundResponse:
    """Return the vendor response an envelope describes."""
    document = json.loads(payload)
    return OutboundResponse(
        status_code=int(document["status_code"]),
        headers={str(k): str(v) for k, v in dict(document.get("headers", {})).items()},
        body=base64.b64decode(str(document.get("body", ""))),
    )


class ProxyApp:
    """The credential proxy as an ASGI callable.

    Mounted in-process by the ``dev`` profile and served by an ASGI server in
    ``standard`` and ``enterprise``. One object, two mount points, and no
    behaviour that depends on which (FR-011).
    """

    __slots__ = ("_engine",)

    def __init__(self, engine: ProxyEngine) -> None:
        self._engine = engine

    @property
    def engine(self) -> ProxyEngine:
        """Return the engine this application serves."""
        return self._engine

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one ASGI request."""
        if scope.get("type") != "http":
            raise ValueError(
                f"the credential proxy serves HTTP only; got a {scope.get('type')!r} scope"
            )

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()

        if path == PROXY_HEALTH_PATH and method == "GET":
            health = await self._engine.health()
            await _respond(send, 200, json.dumps(health.to_record()).encode("utf-8"))
            return

        if path == PROXY_FORWARD_PATH and method == "POST":
            await self._forward(await _read_body(receive), send)
            return

        await _respond(
            send,
            404,
            json.dumps(
                {
                    "reason": str(ProxyErrorReason.MALFORMED_REQUEST),
                    "integration": "",
                    "message": (
                        f"the credential proxy serves {PROXY_FORWARD_PATH} and "
                        f"{PROXY_HEALTH_PATH}; {method} {path} is neither"
                    ),
                    "detail": path,
                    "retryable": False,
                }
            ).encode("utf-8"),
        )

    async def _forward(self, payload: bytes, send: Send) -> None:
        """Decode, forward, and answer — turning any proxy error into a status."""
        try:
            request = decode_forward_request(payload)
            response = await self._engine.forward(request)
        except ProxyError as error:
            await _respond(
                send,
                STATUS_FOR_REASON.get(error.reason, 500),
                json.dumps(error.to_record()).encode("utf-8"),
            )
            return
        await _respond(send, 200, encode_forward_response(response))


def create_proxy_app(engine: ProxyEngine) -> ProxyApp:
    """Return the ASGI application serving ``engine``."""
    return ProxyApp(engine)


async def _read_body(receive: Receive) -> bytes:
    """Return the whole request body, following ASGI's ``more_body`` chaining."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(bytes(message.get("body", b"")))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _respond(send: Send, status: int, body: bytes) -> None:
    """Send one complete JSON response."""
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


__all__ = [
    "STATUS_FOR_REASON",
    "ProxyApp",
    "create_proxy_app",
    "decode_forward_request",
    "decode_forward_response",
    "encode_forward_request",
    "encode_forward_response",
]
