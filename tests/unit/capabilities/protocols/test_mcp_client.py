"""The two transports, and the framing both of them speak.

The interesting assertions here are not about JSON-RPC. They are about the three
things a transport owes the rest of the system whatever wire it uses: a bound on
how long a server may take, a bound on how much it may return, and a refusal to
read a frame that does not say what it claims to.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.protocols.mcp.client import (
    HttpMcpTransport,
    JsonRpcFailure,
    StdioMcpTransport,
    decode_frames,
    encode_frame,
    result_of,
)
from capabilities.protocols.port import MalformedServerResponse
from config.constants.protocols import (
    JSON_RPC_VERSION,
    MAX_PROTOCOL_RESULT_BYTES,
    MCP_METHOD_LIST_TOOLS,
)
from integrations._base.transport import RequestContext
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.sandbox.port import ExecutionRequest, ExecutionResult

pytestmark = pytest.mark.unit


CONTEXT = RequestContext(org_id="acme", team_id="payments", capability="deploys__rollout")
SERVER_URL = "https://mcp.example.test/rpc"


# --- framing --------------------------------------------------------------------


def test_a_frame_carries_the_protocol_version_the_method_and_an_id() -> None:
    frame = json.loads(encode_frame(7, MCP_METHOD_LIST_TOOLS, {}))
    assert frame == {
        "jsonrpc": JSON_RPC_VERSION,
        "id": 7,
        "method": MCP_METHOD_LIST_TOOLS,
        "params": {},
    }


def test_frames_are_read_from_newline_delimited_output() -> None:
    payload = b'{"jsonrpc":"2.0","id":1,"result":{"a":1}}\n\n{"jsonrpc":"2.0","id":2,"result":{}}\n'
    assert [frame["id"] for frame in decode_frames(payload)] == [1, 2]


def test_a_frame_that_is_not_json_is_rejected_naming_the_server() -> None:
    with pytest.raises(MalformedServerResponse) as raised:
        decode_frames(b"not json at all\n", server="deploys")
    assert "deploys" in str(raised.value)


def test_a_frame_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(MalformedServerResponse):
        decode_frames(b"[1, 2, 3]\n", server="deploys")


def test_an_error_frame_becomes_a_failure_carrying_the_servers_own_message() -> None:
    frame = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no such method"}}
    with pytest.raises(JsonRpcFailure) as raised:
        result_of(frame, server="deploys")
    assert "no such method" in str(raised.value)
    assert "-32601" in str(raised.value)


def test_a_frame_with_neither_result_nor_error_is_malformed() -> None:
    with pytest.raises(MalformedServerResponse):
        result_of({"jsonrpc": "2.0", "id": 1}, server="deploys")


def test_a_frame_claiming_the_wrong_protocol_version_is_malformed() -> None:
    with pytest.raises(MalformedServerResponse):
        result_of({"jsonrpc": "1.0", "id": 1, "result": {}}, server="deploys")


# --- HTTP transport, through the credential proxy --------------------------------


def _frame_ids(payload: bytes) -> list[int]:
    """Return the ids of the request frames in ``payload``, in order."""
    return [
        int(json.loads(line)["id"])
        for line in payload.splitlines()
        if line.strip() and "id" in json.loads(line)
    ]


def _answer(payload: Mapping[str, Any], identifier: int) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "result": dict(payload)}).encode()


class RecordingProxy:
    """A ``ProxyTransport`` that answers the frame it was sent and records it."""

    def __init__(
        self,
        result: Mapping[str, Any] | None = None,
        *,
        status: int = 200,
        body: bytes | None = None,
    ) -> None:
        self.result = dict(result or {})
        self.status = status
        self.body = body
        self.requests: list[ProxyRequest] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.requests.append(request)
        if self.body is not None:
            return OutboundResponse(status_code=self.status, body=self.body)
        identifier = _frame_ids(request.body or b"")[-1]
        return OutboundResponse(status_code=self.status, body=_answer(self.result, identifier))


async def test_an_http_call_goes_through_the_proxy_and_carries_no_credential() -> None:
    proxy = RecordingProxy({"tools": []})
    transport = HttpMcpTransport(
        server="deploys",
        transport=proxy,
        context=CONTEXT,
        url=SERVER_URL,
        integration="mcp_deploys",
    )

    await transport.request(MCP_METHOD_LIST_TOOLS, {})

    sent = proxy.requests[0]
    assert sent.integration == "mcp_deploys"
    assert sent.org_id == "acme"
    assert sent.team_id == "payments"
    assert sent.url == SERVER_URL
    # Nothing in the envelope could hold a secret: the proxy injects at the edge.
    assert "authorization" not in {name.lower() for name in sent.headers}


async def test_an_http_call_returns_the_json_rpc_result() -> None:
    proxy = RecordingProxy({"tools": [{"name": "rollout"}]})
    transport = HttpMcpTransport(
        server="deploys",
        transport=proxy,
        context=CONTEXT,
        url=SERVER_URL,
        integration="mcp_deploys",
    )

    result = await transport.request(MCP_METHOD_LIST_TOOLS, {})

    assert result == {"tools": [{"name": "rollout"}]}


async def test_a_non_2xx_answer_is_a_malformed_response_not_a_parse_failure() -> None:
    proxy = RecordingProxy(status=504, body=b"<html>gateway timeout</html>")
    transport = HttpMcpTransport(
        server="deploys",
        transport=proxy,
        context=CONTEXT,
        url=SERVER_URL,
        integration="mcp_deploys",
    )

    with pytest.raises(MalformedServerResponse) as raised:
        await transport.request(MCP_METHOD_LIST_TOOLS, {})
    assert "504" in str(raised.value)


async def test_an_answer_larger_than_the_cap_is_refused_rather_than_read() -> None:
    proxy = RecordingProxy(body=b"x" * (MAX_PROTOCOL_RESULT_BYTES + 1))
    transport = HttpMcpTransport(
        server="deploys",
        transport=proxy,
        context=CONTEXT,
        url=SERVER_URL,
        integration="mcp_deploys",
    )

    with pytest.raises(MalformedServerResponse) as raised:
        await transport.request(MCP_METHOD_LIST_TOOLS, {})
    assert str(MAX_PROTOCOL_RESULT_BYTES) in str(raised.value)


async def test_a_slow_server_times_out_rather_than_holding_the_turn() -> None:
    class Slow:
        async def forward(self, request: ProxyRequest) -> OutboundResponse:
            await asyncio.sleep(5)
            return OutboundResponse(status_code=200)

    transport = HttpMcpTransport(
        server="deploys", transport=Slow(), context=CONTEXT, url=SERVER_URL, integration="mcp_dep"
    )

    with pytest.raises(TimeoutError):
        await transport.request(MCP_METHOD_LIST_TOOLS, {}, timeout_seconds=0.01)


# --- stdio transport, inside the sandbox -----------------------------------------


class ScriptedSandbox:
    """A ``Sandbox`` that answers the frame it was handed on stdin.

    Answering the *sent* id rather than a fixed one is what makes the
    wrong-answer test below mean something: the failure has to be produced by a
    server that genuinely replied to something else.
    """

    def __init__(
        self,
        result: Mapping[str, Any] | None = None,
        *,
        exit_code: int = 0,
        stderr: bytes = b"",
        answer_id: int | None = None,
    ) -> None:
        self._result = dict(result or {})
        self._exit_code = exit_code
        self._stderr = stderr
        self._answer_id = answer_id
        self.requests: list[ExecutionRequest] = []
        self.provisioned = 0
        self.released = 0

    async def provision(self, spec: Any) -> Any:
        self.provisioned += 1
        return object()

    async def execute(self, instance: Any, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        if self._exit_code:
            return ExecutionResult(exit_code=self._exit_code, stderr=self._stderr)
        identifier = (
            self._answer_id if self._answer_id is not None else _frame_ids(request.stdin)[-1]
        )
        return ExecutionResult(exit_code=0, stdout=_answer(self._result, identifier))

    async def release(self, instance: Any) -> None:
        self.released += 1


async def test_a_stdio_server_runs_inside_the_sandbox_and_never_as_a_bare_process() -> None:
    sandbox = ScriptedSandbox({"tools": []})
    transport = StdioMcpTransport(
        server="deploys", sandbox=sandbox, spec=object(), command=("mcp-deploys", "--stdio")
    )

    await transport.request(MCP_METHOD_LIST_TOOLS, {})

    assert sandbox.provisioned == 1
    assert sandbox.requests[0].command == ("mcp-deploys", "--stdio")
    # Initialise, initialised, then the call itself: three frames on stdin.
    assert sandbox.requests[0].stdin.count(b"\n") >= 3


async def test_a_stdio_server_carries_no_credential_in_its_environment() -> None:
    sandbox = ScriptedSandbox({"tools": []})
    transport = StdioMcpTransport(
        server="deploys", sandbox=sandbox, spec=object(), command=("mcp-deploys",)
    )

    await transport.request(MCP_METHOD_LIST_TOOLS, {})

    assert dict(sandbox.requests[0].environment) == {}


async def test_a_stdio_server_that_exits_non_zero_is_a_malformed_response() -> None:
    sandbox = ScriptedSandbox(exit_code=1, stderr=b"config file missing")
    transport = StdioMcpTransport(
        server="deploys", sandbox=sandbox, spec=object(), command=("mcp-deploys",)
    )

    with pytest.raises(MalformedServerResponse) as raised:
        await transport.request(MCP_METHOD_LIST_TOOLS, {})
    assert "config file missing" in str(raised.value)


async def test_a_stdio_server_that_answers_a_different_request_is_malformed() -> None:
    sandbox = ScriptedSandbox({"tools": []}, answer_id=99_999)
    transport = StdioMcpTransport(
        server="deploys", sandbox=sandbox, spec=object(), command=("mcp-deploys",)
    )

    with pytest.raises(MalformedServerResponse):
        await transport.request(MCP_METHOD_LIST_TOOLS, {})


async def test_closing_a_stdio_transport_releases_its_sandbox() -> None:
    sandbox = ScriptedSandbox({"tools": []})
    transport = StdioMcpTransport(
        server="deploys", sandbox=sandbox, spec=object(), command=("mcp-deploys",)
    )

    await transport.request(MCP_METHOD_LIST_TOOLS, {})
    await transport.close()

    assert sandbox.released == 1
