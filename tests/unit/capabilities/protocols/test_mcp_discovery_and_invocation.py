"""Reading a server's catalogue and calling one of its tools.

SC-008 lives here in both halves: a malformed *schema* and a malformed
*response* each produce a specific error and neither takes the catalogue or the
turn with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.protocols.mcp.adapter import McpAdapter
from capabilities.protocols.mcp.discovery import (
    discovered_tools,
    suggested_side_effect,
    tool_from_declaration,
)
from capabilities.protocols.mcp.invocation import invoke_tool, read_content
from capabilities.protocols.port import (
    ExclusionReason,
    MalformedServerResponse,
    MalformedToolSchema,
    ProtocolKind,
)
from config.constants.protocols import (
    MAX_PROTOCOL_RESULT_BYTES,
    MCP_METHOD_CALL_TOOL,
    MCP_METHOD_LIST_TOOLS,
    MCP_METHOD_PING,
)
from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass

pytestmark = pytest.mark.unit


class ScriptedTransport:
    """An ``McpTransport`` that answers each method from a script."""

    def __init__(self, answers: Mapping[str, Any], *, server: str = "deploys") -> None:
        self._answers = dict(answers)
        self._server = server
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = 0

    @property
    def server(self) -> str:
        return self._server

    async def request(
        self, method: str, params: Mapping[str, Any], *, timeout_seconds: float = 1.0
    ) -> Any:
        self.calls.append((method, dict(params)))
        answer = self._answers.get(method)
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer(params)
        if answer is None:
            raise MalformedServerResponse(f"{self._server} does not implement {method}")
        return answer

    async def close(self) -> None:
        self.closed += 1


OBJECT_SCHEMA = {"type": "object", "properties": {"target": {"type": "string"}}}


def _declaration(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Does a thing.",
        "inputSchema": dict(OBJECT_SCHEMA),
    } | extra


# --- declarations ----------------------------------------------------------------


def test_a_declaration_becomes_a_bridged_tool() -> None:
    declared = tool_from_declaration(_declaration("rollout"), server="deploys")
    assert declared.qualified_name == "deploys.rollout"
    assert declared.catalogue_name == "deploys__rollout"
    assert declared.description == "Does a thing."


def test_a_declaration_with_no_name_is_rejected_specifically() -> None:
    with pytest.raises(MalformedServerResponse) as raised:
        tool_from_declaration({"description": "no name"}, server="deploys")
    assert "deploys" in str(raised.value)
    assert "name" in str(raised.value)


def test_a_declaration_that_is_not_an_object_is_rejected_specifically() -> None:
    with pytest.raises(MalformedServerResponse):
        tool_from_declaration("rollout", server="deploys")


def test_a_declaration_with_a_malformed_schema_is_rejected_specifically() -> None:
    with pytest.raises(MalformedToolSchema) as raised:
        tool_from_declaration(
            _declaration("rollout", inputSchema={"type": "object", "properties": []}),
            server="deploys",
        )
    assert "deploys.rollout" in str(raised.value)


def test_the_servers_hints_are_kept_as_a_suggestion() -> None:
    assert suggested_side_effect({"readOnlyHint": True}) == SideEffectLevel.READ.value
    assert suggested_side_effect({"destructiveHint": True}) == SideEffectLevel.DESTRUCTIVE.value
    assert suggested_side_effect({}) == ""

    declared = tool_from_declaration(
        _declaration("status", annotations={"readOnlyHint": True}), server="deploys"
    )
    assert declared.declared_side_effect == SideEffectLevel.READ.value


# --- listing ---------------------------------------------------------------------


async def test_a_tool_list_becomes_a_discovery() -> None:
    transport = ScriptedTransport(
        {MCP_METHOD_LIST_TOOLS: {"tools": [_declaration("rollout"), _declaration("status")]}}
    )

    discovery = await discovered_tools(transport)

    assert [item.tool for item in discovery.tools] == ["rollout", "status"]
    assert discovery.offered == 2
    assert discovery.excluded == ()


async def test_a_malformed_entry_is_excluded_and_the_rest_of_the_list_survives() -> None:
    # SC-008, the schema half: one bad declaration must not cost the catalogue.
    transport = ScriptedTransport(
        {
            MCP_METHOD_LIST_TOOLS: {
                "tools": [
                    _declaration("rollout"),
                    _declaration("broken", inputSchema={"type": "object", "properties": 7}),
                    _declaration("status"),
                ]
            }
        }
    )

    discovery = await discovered_tools(transport)

    assert [item.tool for item in discovery.tools] == ["rollout", "status"]
    assert len(discovery.excluded) == 1
    assert discovery.excluded[0].reason is ExclusionReason.MALFORMED_SCHEMA
    assert discovery.excluded[0].tool == "broken"
    assert "properties" in discovery.excluded[0].detail


async def test_an_unnormalisable_schema_is_excluded_with_its_own_reason() -> None:
    transport = ScriptedTransport(
        {
            MCP_METHOD_LIST_TOOLS: {
                "tools": [
                    _declaration("rollout"),
                    _declaration("weird", inputSchema={"type": "array", "items": {}}),
                ]
            }
        }
    )

    discovery = await discovered_tools(transport)

    assert [item.tool for item in discovery.tools] == ["rollout"]
    assert discovery.excluded[0].reason is ExclusionReason.UNNORMALISABLE_SCHEMA


async def test_a_list_that_is_not_a_list_is_rejected_specifically() -> None:
    transport = ScriptedTransport({MCP_METHOD_LIST_TOOLS: {"tools": "rollout"}})
    with pytest.raises(MalformedServerResponse) as raised:
        await discovered_tools(transport)
    assert "deploys" in str(raised.value)


async def test_pagination_is_followed_and_bounded() -> None:
    pages = {
        "": {"tools": [_declaration("a")], "nextCursor": "p1"},
        "p1": {"tools": [_declaration("b")], "nextCursor": "p2"},
        "p2": {"tools": [_declaration("c")]},
    }
    transport = ScriptedTransport(
        {MCP_METHOD_LIST_TOOLS: lambda params: pages[params.get("cursor", "")]}
    )

    discovery = await discovered_tools(transport)

    assert [item.tool for item in discovery.tools] == ["a", "b", "c"]


async def test_a_cursor_that_never_ends_stops_at_the_page_limit() -> None:
    transport = ScriptedTransport(
        {MCP_METHOD_LIST_TOOLS: lambda _: {"tools": [_declaration("a")], "nextCursor": "more"}}
    )

    discovery = await discovered_tools(transport, page_limit=3)

    assert discovery.offered == 3


# --- calling ---------------------------------------------------------------------


async def test_a_call_returns_the_servers_content_as_data() -> None:
    transport = ScriptedTransport(
        {MCP_METHOD_CALL_TOOL: {"content": [{"type": "text", "text": "rolled back to v41"}]}}
    )

    result = await invoke_tool(transport, tool="rollout", arguments={"target": "web"})

    assert result.succeeded
    assert result.value["text"] == "rolled back to v41"
    assert result.value["server"] == "deploys"
    assert transport.calls[0] == (
        MCP_METHOD_CALL_TOOL,
        {"name": "rollout", "arguments": {"target": "web"}},
    )


async def test_structured_content_is_kept_alongside_the_text() -> None:
    transport = ScriptedTransport(
        {
            MCP_METHOD_CALL_TOOL: {
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {"version": 41},
            }
        }
    )

    result = await invoke_tool(transport, tool="rollout", arguments={})

    assert result.value["structured"] == {"version": 41}


async def test_a_tool_error_is_a_classified_failure_not_a_success() -> None:
    transport = ScriptedTransport(
        {
            MCP_METHOD_CALL_TOOL: {
                "isError": True,
                "content": [{"type": "text", "text": "no such deployment"}],
            }
        }
    )

    result = await invoke_tool(transport, tool="rollout", arguments={})

    assert not result.succeeded
    assert result.error_class is CapabilityErrorClass.UPSTREAM_ERROR
    assert "no such deployment" in result.detail


async def test_a_malformed_response_is_a_classified_failure_naming_the_shape() -> None:
    # SC-008, the response half.
    transport = ScriptedTransport({MCP_METHOD_CALL_TOOL: {"nothing": "useful"}})

    result = await invoke_tool(transport, tool="rollout", arguments={})

    assert not result.succeeded
    assert result.error_class is CapabilityErrorClass.UPSTREAM_ERROR
    assert "structuredContent" in result.detail


async def test_a_timeout_is_classified_as_a_timeout() -> None:
    transport = ScriptedTransport({MCP_METHOD_CALL_TOOL: TimeoutError()})

    result = await invoke_tool(transport, tool="rollout", arguments={}, timeout_seconds=0.5)

    assert result.error_class is CapabilityErrorClass.TIMEOUT
    assert "0.5" in result.message


def test_content_larger_than_the_cap_is_truncated_and_says_so() -> None:
    payload = {"content": [{"type": "text", "text": "x" * (MAX_PROTOCOL_RESULT_BYTES + 100)}]}

    value, truncated = read_content(payload, server="deploys", tool="dump")

    assert truncated
    assert len(value["text"].encode()) <= MAX_PROTOCOL_RESULT_BYTES


def test_a_content_block_this_bridge_cannot_read_is_summarised_rather_than_dropped() -> None:
    payload = {"content": [{"type": "image", "data": "…"}]}

    value, _ = read_content(payload, server="deploys", tool="screenshot")

    assert value["blocks"][0]["type"] == "image"


# --- the adapter -------------------------------------------------------------------


async def test_the_adapter_reports_a_server_it_does_not_hold_as_unavailable() -> None:
    adapter = McpAdapter({})

    assert adapter.kind is ProtocolKind.MCP
    assert (await adapter.discover("deploys")).tools == ()
    assert not (await adapter.health("deploys")).reachable

    result = await adapter.invoke("deploys", "rollout", {})
    assert result.error_class is CapabilityErrorClass.UNAVAILABLE


async def test_the_adapter_reports_a_server_that_fails_to_list_as_unavailable() -> None:
    transport = ScriptedTransport({MCP_METHOD_LIST_TOOLS: MalformedServerResponse("gone")})
    adapter = McpAdapter({"deploys": transport})

    assert (await adapter.discover("deploys")).tools == ()
    assert not (await adapter.health("deploys")).reachable


async def test_the_adapter_pings_for_health_and_lists_for_describe() -> None:
    transport = ScriptedTransport(
        {
            MCP_METHOD_PING: {},
            MCP_METHOD_LIST_TOOLS: {"tools": [_declaration("rollout")]},
        }
    )
    adapter = McpAdapter({"deploys": transport})

    assert (await adapter.health("deploys")).reachable
    described = await adapter.describe("deploys", "rollout")
    assert described is not None and described.tool == "rollout"
    assert await adapter.describe("deploys", "nonexistent") is None


async def test_closing_the_adapter_closes_every_transport() -> None:
    transport = ScriptedTransport({MCP_METHOD_PING: {}})
    adapter = McpAdapter({"deploys": transport})

    await adapter.close()

    assert transport.closed == 1
