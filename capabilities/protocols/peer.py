"""One HTTP-JSON transport, shared by the two protocols that are not MCP.

ACP and OpenClaw differ from MCP in their document shapes and from each other in
their paths. Neither differs in what a bridge owes: the call goes through the
credential proxy, it is bounded in time, it is bounded in bytes, and a
non-JSON answer is a named failure rather than an exception from ``json``.

Written once here so that "governed identically" is a property of the code
rather than of two adapters remembering to agree. ``mcp/client.py`` keeps its own
because JSON-RPC framing is not a document GET.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, Final, Protocol, runtime_checkable
from urllib.parse import urljoin

from capabilities.protocols.port import MalformedServerResponse
from config.constants.protocols import (
    MAX_PROTOCOL_RESULT_BYTES,
    PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
)
from integrations._base.errors import IntegrationError
from integrations._base.transport import ProxyTransport, RequestContext
from platform.credentials.proxy.model import ProxyRequest

JSON_CONTENT_TYPE: Final = "application/json"


@runtime_checkable
class PeerTransport(Protocol):
    """Fetches and posts JSON documents at one registered peer."""

    @property
    def server(self) -> str:
        """Return the registered server this transport reaches."""

    async def get_json(
        self, path: str, *, timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS
    ) -> Any:
        """Return the document at ``path``, relative to the peer's base URL."""

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> Any:
        """Return the document the peer answered ``payload`` with."""

    async def close(self) -> None:
        """Release whatever this transport holds. Idempotent."""


class ProxyPeerTransport:
    """A peer reached over HTTPS, through the credential proxy.

    Same discipline as ``HttpMcpTransport`` and for the same reason: there is no
    constructor parameter here that could hold a credential, because the secret
    is attached at the network edge from a handle this process cannot read.
    """

    __slots__ = ("_base_url", "_context", "_integration", "_server", "_transport")

    def __init__(
        self,
        *,
        server: str,
        transport: ProxyTransport,
        context: RequestContext,
        base_url: str,
        integration: str,
    ) -> None:
        self._server = server
        self._transport = transport
        self._context = context
        self._base_url = base_url if base_url.endswith("/") else base_url + "/"
        self._integration = integration

    @property
    def server(self) -> str:
        """Return the registered server this transport reaches."""
        return self._server

    async def get_json(
        self, path: str, *, timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS
    ) -> Any:
        """Return the document at ``path``."""
        return await self._send("GET", path, None, timeout_seconds)

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> Any:
        """Return the document the peer answered ``payload`` with."""
        return await self._send("POST", path, dict(payload), timeout_seconds)

    async def close(self) -> None:
        """Release nothing: an HTTP transport holds no peer."""

    async def _send(
        self, method: str, path: str, payload: Mapping[str, Any] | None, timeout_seconds: float
    ) -> Any:
        request = ProxyRequest(
            integration=self._integration,
            org_id=self._context.org_id,
            team_id=self._context.team_id,
            capability=self._context.capability,
            method=method,
            url=urljoin(self._base_url, path.lstrip("/")),
            headers={"Accept": JSON_CONTENT_TYPE}
            | ({"Content-Type": JSON_CONTENT_TYPE} if payload is not None else {}),
            body=json.dumps(payload).encode("utf-8") if payload is not None else None,
        )

        try:
            response = await asyncio.wait_for(
                self._transport.forward(request), timeout=timeout_seconds
            )
        except IntegrationError as error:
            raise MalformedServerResponse(
                f"{self._server} could not be reached through the credential proxy: {error}"
            ) from error

        if not response.succeeded:
            raise MalformedServerResponse(
                f"{self._server} answered HTTP {response.status_code} to {method} {path}"
            )
        if len(response.body) > MAX_PROTOCOL_RESULT_BYTES:
            raise MalformedServerResponse(
                f"{self._server} answered {len(response.body)} bytes, over the "
                f"{MAX_PROTOCOL_RESULT_BYTES}-byte cap on a bridged answer"
            )
        try:
            return json.loads(response.body or b"null")
        except json.JSONDecodeError as error:
            raise MalformedServerResponse(
                f"{self._server} answered {method} {path} with a body that is not JSON: {error.msg}"
            ) from error


__all__ = ["JSON_CONTENT_TYPE", "PeerTransport", "ProxyPeerTransport"]
