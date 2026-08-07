"""One scripted protocol adapter, and the fixtures built on it.

Deliberately dumb: it answers from a dictionary and counts what it was asked.
Every assertion in these tests is then about the bridge's governance rather
than about a mock that was taught to agree with it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ProtocolKind,
)
from core.capability.result import CapabilityErrorClass

#: The shape a well-behaved server declares for a tool taking one argument.
OBJECT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"target": {"type": "string"}},
    "required": ["target"],
}


def offered(
    server: str,
    tool: str,
    *,
    description: str = "Do the thing the server does.",
    declared: str = "",
    schema: Mapping[str, Any] | None = None,
) -> BridgedTool:
    """Return one tool as a server would declare it."""
    return BridgedTool(
        server=server,
        tool=tool,
        description=description,
        input_schema=dict(schema if schema is not None else OBJECT_SCHEMA),
        declared_side_effect=declared,
    )


class ScriptedAdapter:
    """A ``ProtocolAdapter`` that answers from a fixture and records its calls."""

    def __init__(
        self,
        *,
        tools: Sequence[BridgedTool] = (),
        results: Mapping[str, BridgedResult] | None = None,
        reachable: bool = True,
        kind: ProtocolKind = ProtocolKind.MCP,
        offered_count: int = 0,
    ) -> None:
        self._tools = tuple(tools)
        self._results = dict(results or {})
        self._reachable = reachable
        self._kind = kind
        self._offered = offered_count
        self.invocations: list[tuple[str, str, dict[str, Any]]] = []

    @property
    def kind(self) -> ProtocolKind:
        """Return which wire protocol this adapter pretends to speak."""
        return self._kind

    async def discover(self, server: str) -> Discovery:
        """Return the scripted tool list for ``server``."""
        if not self._reachable:
            return Discovery(server=server)
        tools = tuple(found for found in self._tools if found.server == server)
        return Discovery(server=server, tools=tools, offered=self._offered or len(tools))

    async def describe(self, server: str, tool: str) -> BridgedTool | None:
        """Return one scripted declaration, or ``None``."""
        for found in self._tools:
            if found.server == server and found.tool == tool:
                return found
        return None

    async def invoke(self, server: str, tool: str, arguments: Mapping[str, Any]) -> BridgedResult:
        """Return the scripted answer, recording that it was asked for."""
        self.invocations.append((server, tool, dict(arguments)))
        if not self._reachable:
            return BridgedResult.failure(
                CapabilityErrorClass.UNAVAILABLE, f"{server} is not answering"
            )
        scripted = self._results.get(f"{server}.{tool}")
        if scripted is not None:
            return scripted
        return BridgedResult.ok({"server": server, "tool": tool, "arguments": dict(arguments)})

    async def health(self, server: str) -> BridgeHealth:
        """Return the scripted health of ``server``."""
        if self._reachable:
            return BridgeHealth.up(server)
        return BridgeHealth.down(server, "connection refused")
