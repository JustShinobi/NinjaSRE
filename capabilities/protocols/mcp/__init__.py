"""MCP: the primary protocol, in four parts.

``client``
    The two transports. HTTP goes through the credential proxy, so a server
    requiring authentication is reached with a secret this process never holds.
    stdio runs the server's command *inside a sandbox* — a local program a
    third party wrote is exactly what the sandbox exists for.

``discovery``
    ``tools/list`` to a set of ``BridgedTool``s, with malformed declarations
    rejected by name and unnormalisable schemas excluded with a reason.

``invocation``
    ``tools/call`` to a ``BridgedResult``: bounded in time, bounded in size, and
    with the server's content treated as data on the way back.

``adapter``
    The three composed into one ``ProtocolAdapter``.
"""

from __future__ import annotations

from capabilities.protocols.mcp.adapter import McpAdapter
from capabilities.protocols.mcp.client import (
    HttpMcpTransport,
    JsonRpcFailure,
    McpTransport,
    StdioMcpTransport,
)
from capabilities.protocols.mcp.discovery import discovered_tools, tool_from_declaration
from capabilities.protocols.mcp.invocation import invoke_tool, read_content

__all__ = [
    "HttpMcpTransport",
    "JsonRpcFailure",
    "McpAdapter",
    "McpTransport",
    "StdioMcpTransport",
    "discovered_tools",
    "invoke_tool",
    "read_content",
    "tool_from_declaration",
]
