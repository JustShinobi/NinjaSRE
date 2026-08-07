"""Two ways to reach an MCP server, and the framing both of them speak.

The transports differ in where the server runs; they do not differ in what the
rest of the bridge is promised. Each one bounds the wall clock, bounds the bytes
it will read, and refuses a frame that does not say what it claims to — because
those three are what stop a server nobody here operates from stalling a turn,
filling a trace, or being believed.

**HTTP goes through the credential proxy.** A ``ProxyRequest`` carries an
organisation, a team, a capability, and a server name; the secret is attached at
the network edge. There is no parameter here that could accept a credential,
which is the same property ``integrations/_base/client.py`` has and for the same
reason.

**stdio runs inside a sandbox.** A local program written by a third party is
precisely what the sandbox is for, and running one with ``create_subprocess_exec``
would put it on the host with the agent's own file descriptors. One exchange is
one ``execute``: initialise, initialised, the call, then EOF — an MCP server
reading stdin exits when it closes, so there is no long-lived process to reap
and no state to carry between calls. The cost is one process per exchange; the
benefit is that a bridged server has no lifetime the reaper does not already
understand.

Neither transport puts anything in the server's environment. Article IV forbids
a credential there, and an environment that carries *anything* is an environment
somebody eventually puts one in.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from capabilities.protocols.port import MalformedServerResponse, ProtocolBridgeError
from config.constants.protocols import (
    JSON_RPC_VERSION,
    MAX_PROTOCOL_RESULT_BYTES,
    MCP_METHOD_INITIALIZE,
    MCP_PROTOCOL_VERSION,
    PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
)
from integrations._base.errors import IntegrationError
from integrations._base.transport import ProxyTransport, RequestContext
from platform.credentials.proxy.model import ProxyRequest
from platform.sandbox.port import ExecutionRequest, Sandbox, SandboxInstance
from platform.sandbox.spec import SandboxSpec

#: What this client tells a server about itself on initialise. A name and a
#: version, and nothing about the deployment: a bridged server has no business
#: knowing whose incident it is being asked about.
CLIENT_INFO: Mapping[str, str] = {"name": "ninjasre", "version": "1"}

#: The content type an MCP HTTP endpoint speaks.
JSON_CONTENT_TYPE = "application/json"

#: Frame ids, monotonic within the process. A server that answers the wrong id
#: is answering somebody else's question, and matching on it is the only way to
#: notice.
_IDS = itertools.count(1)


class JsonRpcFailure(ProtocolBridgeError):
    """The server answered with an error frame rather than a result."""

    def __init__(self, server: str, *, code: int, message: str) -> None:
        super().__init__(f"{server} refused the call: {message} (JSON-RPC code {code})")
        self.server = server
        self.code = code
        self.detail = message


@runtime_checkable
class McpTransport(Protocol):
    """Carries one JSON-RPC request to a server and brings the result back."""

    @property
    def server(self) -> str:
        """Return the registered server this transport reaches."""

    async def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> Any:
        """Return the ``result`` member of the server's answer.

        Raises ``MalformedServerResponse`` for anything that is not a well-formed
        answer to this request, ``JsonRpcFailure`` for an error frame, and
        ``TimeoutError`` when the server took longer than it was given.
        """

    async def close(self) -> None:
        """Release whatever this transport holds. Idempotent."""


def encode_frame(identifier: int, method: str, params: Mapping[str, Any]) -> bytes:
    """Return one JSON-RPC request frame as it goes on the wire."""
    return json.dumps(
        {
            "jsonrpc": JSON_RPC_VERSION,
            "id": identifier,
            "method": method,
            "params": dict(params),
        }
    ).encode("utf-8")


def encode_notification(method: str, params: Mapping[str, Any]) -> bytes:
    """Return one JSON-RPC notification — a frame with no id and no answer."""
    return json.dumps(
        {"jsonrpc": JSON_RPC_VERSION, "method": method, "params": dict(params)}
    ).encode("utf-8")


def decode_frames(payload: bytes, *, server: str = "") -> list[dict[str, Any]]:
    """Return every JSON-RPC frame in ``payload``, or raise naming the server.

    Newline-delimited, which is what an MCP stdio server writes and what an HTTP
    endpoint's single-frame body degenerates to. A blank line is skipped; a line
    that is not a JSON object is a protocol violation rather than something to
    step over, because silently skipping it turns "the server is broken" into
    "the server has no tools".
    """
    frames: list[dict[str, Any]] = []
    for line in payload.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as error:
            raise MalformedServerResponse(
                f"{server or 'the server'} answered with a line that is not JSON: {error.msg}"
            ) from error
        if not isinstance(decoded, dict):
            raise MalformedServerResponse(
                f"{server or 'the server'} answered with a "
                f"{type(decoded).__name__} where a JSON-RPC frame belongs"
            )
        frames.append(decoded)
    return frames


def result_of(frame: Mapping[str, Any], *, server: str) -> Any:
    """Return the ``result`` in ``frame``, or raise saying what arrived instead."""
    version = frame.get("jsonrpc")
    if version != JSON_RPC_VERSION:
        raise MalformedServerResponse(
            f"{server} answered with jsonrpc {version!r}; this bridge speaks {JSON_RPC_VERSION}"
        )

    error = frame.get("error")
    if isinstance(error, Mapping):
        raise JsonRpcFailure(
            server,
            code=int(error.get("code", 0) or 0),
            message=str(error.get("message", "no message")),
        )

    if "result" not in frame:
        raise MalformedServerResponse(
            f"{server} answered a frame carrying neither a result nor an error, so "
            f"there is nothing to read from it"
        )
    return frame["result"]


def _within_cap(payload: bytes, *, server: str) -> bytes:
    """Return ``payload`` when it fits the result cap, or raise naming the cap."""
    if len(payload) > MAX_PROTOCOL_RESULT_BYTES:
        raise MalformedServerResponse(
            f"{server} answered {len(payload)} bytes, over the "
            f"{MAX_PROTOCOL_RESULT_BYTES}-byte cap on a bridged answer — narrow the "
            f"request or the server's own limits"
        )
    return payload


def _answer_to(frames: Sequence[Mapping[str, Any]], identifier: int, *, server: str) -> Any:
    """Return the result of the frame answering ``identifier``."""
    for frame in frames:
        if frame.get("id") == identifier:
            return result_of(frame, server=server)
    raise MalformedServerResponse(
        f"{server} answered {len(frames)} frames and none of them carries id "
        f"{identifier}, so nothing here is an answer to the request that was sent"
    )


class HttpMcpTransport:
    """An MCP server over HTTP, reached through the credential proxy.

    ``integration`` is the name the proxy resolves a credential and an egress
    allow-list under. A registered server gets its own, so one team's bridged
    server cannot borrow another's credential and cannot reach another's hosts.
    """

    __slots__ = ("_context", "_integration", "_server", "_transport", "_url")

    def __init__(
        self,
        *,
        server: str,
        transport: ProxyTransport,
        context: RequestContext,
        url: str,
        integration: str,
    ) -> None:
        self._server = server
        self._transport = transport
        self._context = context
        self._url = url
        self._integration = integration

    @property
    def server(self) -> str:
        """Return the registered server this transport reaches."""
        return self._server

    async def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> Any:
        """Return the server's result for one JSON-RPC call."""
        identifier = next(_IDS)
        request = ProxyRequest(
            integration=self._integration,
            org_id=self._context.org_id,
            team_id=self._context.team_id,
            capability=self._context.capability,
            method="POST",
            url=self._url,
            headers={"Content-Type": JSON_CONTENT_TYPE, "Accept": JSON_CONTENT_TYPE},
            body=encode_frame(identifier, method, params),
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
                f"{self._server} answered HTTP {response.status_code}, which is not an MCP frame"
            )

        frames = decode_frames(_within_cap(response.body, server=self._server), server=self._server)
        return _answer_to(frames, identifier, server=self._server)

    async def close(self) -> None:
        """Release nothing: an HTTP transport holds no server."""


class StdioMcpTransport:
    """An MCP server run as a local command, inside a sandbox.

    One exchange is one sandboxed run. The initialise handshake is replayed each
    time, which costs a round trip inside a process that was going to start
    anyway and buys the property that matters: there is no bridged server
    holding a sandbox open across investigations, and nothing for the reaper to
    learn about.
    """

    __slots__ = ("_command", "_instance", "_sandbox", "_server", "_spec")

    def __init__(
        self,
        *,
        server: str,
        sandbox: Sandbox,
        spec: SandboxSpec,
        command: Sequence[str],
    ) -> None:
        self._server = server
        self._sandbox = sandbox
        self._spec = spec
        self._command = tuple(command)
        self._instance: SandboxInstance | None = None

    @property
    def server(self) -> str:
        """Return the registered server this transport reaches."""
        return self._server

    async def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> Any:
        """Return the server's result for one JSON-RPC call."""
        identifier = next(_IDS)
        stdin = b"\n".join(
            (
                encode_frame(
                    next(_IDS),
                    MCP_METHOD_INITIALIZE,
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": dict(CLIENT_INFO),
                    },
                ),
                encode_notification("notifications/initialized", {}),
                encode_frame(identifier, method, params),
                b"",
            )
        )

        sandbox = self._sandbox
        instance = await self._provisioned()
        result = await sandbox.execute(
            instance,
            ExecutionRequest(
                command=self._command,
                stdin=stdin,
                # Empty, and it stays empty. Article IV forbids a credential
                # here, and an environment carrying anything is one somebody
                # eventually puts a credential in.
                environment={},
                timeout_seconds=timeout_seconds,
            ),
        )

        if not result.succeeded:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise MalformedServerResponse(
                f"{self._server} exited {result.exit_code} without answering"
                + (f": {detail}" if detail else "")
            )

        frames = decode_frames(_within_cap(result.stdout, server=self._server), server=self._server)
        return _answer_to(frames, identifier, server=self._server)

    async def close(self) -> None:
        """Release the sandbox this transport provisioned, if it provisioned one."""
        if self._instance is None:
            return
        instance, self._instance = self._instance, None
        await self._sandbox.release(instance)

    async def _provisioned(self) -> SandboxInstance:
        """Return this transport's sandbox, provisioning it the first time."""
        if self._instance is None:
            self._instance = await self._sandbox.provision(self._spec)
        return self._instance


__all__ = [
    "CLIENT_INFO",
    "HttpMcpTransport",
    "JsonRpcFailure",
    "McpTransport",
    "StdioMcpTransport",
    "decode_frames",
    "encode_frame",
    "encode_notification",
    "result_of",
]
