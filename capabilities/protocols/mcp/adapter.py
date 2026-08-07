"""The MCP ``ProtocolAdapter``: transports, discovery, and invocation composed.

One adapter holds every server a team has registered, keyed by name, because the
catalogue asks it about each server in turn and a per-server adapter would put
that loop one layer higher for no gain.

Nothing here decides anything about governance. It reads a server's answer and
turns it into the port's vocabulary; the cap, the classification, and the
refusal all live in ``protocols/catalogue.py``, where all three protocols get
them identically.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.protocols.mcp.client import McpTransport
from capabilities.protocols.mcp.discovery import discovered_tools
from capabilities.protocols.mcp.invocation import invoke_tool
from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ProtocolBridgeError,
    ProtocolKind,
)
from config.constants.protocols import (
    MCP_METHOD_PING,
    PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
    PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
)
from core.capability.result import CapabilityErrorClass
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class McpAdapter:
    """Every MCP server one team has registered, behind the four-operation port."""

    __slots__ = ("_discovery_timeout", "_invocation_timeout", "_transports")

    def __init__(
        self,
        transports: Mapping[str, McpTransport],
        *,
        discovery_timeout_seconds: float = PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
        invocation_timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> None:
        self._transports = dict(transports)
        self._discovery_timeout = discovery_timeout_seconds
        self._invocation_timeout = invocation_timeout_seconds

    @property
    def kind(self) -> ProtocolKind:
        """Return which wire protocol this adapter speaks."""
        return ProtocolKind.MCP

    @property
    def servers(self) -> tuple[str, ...]:
        """Return every registered server this adapter can reach, in name order."""
        return tuple(sorted(self._transports))

    async def discover(self, server: str) -> Discovery:
        """Return what ``server`` offers, empty when it could not be asked.

        Empty rather than raised. The catalogue confirms an empty answer against
        ``health`` before deciding a server is down, so a server that genuinely
        offers nothing and a server that is unreachable are told apart rather
        than conflated (FR-007).
        """
        transport = self._transports.get(server)
        if transport is None:
            return Discovery(server=server)
        try:
            return await discovered_tools(transport, timeout_seconds=self._discovery_timeout)
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            logger.warning("protocols.mcp.list_failed", server=server, error=str(error))
            return Discovery(server=server)

    async def describe(self, server: str, tool: str) -> BridgedTool | None:
        """Return one tool's declaration, or ``None`` when the server has no such tool.

        Re-listing rather than caching. A description read from a cache is a
        description of what the server offered last time, and a refresh that
        reported the old answer would defeat the purpose of asking.
        """
        for declared in (await self.discover(server)).tools:
            if declared.tool == tool:
                return declared
        return None

    async def invoke(self, server: str, tool: str, arguments: Mapping[str, Any]) -> BridgedResult:
        """Return what one call produced, classified rather than raised."""
        transport = self._transports.get(server)
        if transport is None:
            return BridgedResult.failure(
                CapabilityErrorClass.UNAVAILABLE,
                f"{server} is not a server this team has registered",
            )
        return await invoke_tool(
            transport,
            tool=tool,
            arguments=arguments,
            timeout_seconds=self._invocation_timeout,
        )

    async def health(self, server: str) -> BridgeHealth:
        """Return whether ``server`` answers a ping, and what it said if not."""
        transport = self._transports.get(server)
        if transport is None:
            return BridgeHealth.down(server, "not registered for this team")
        try:
            await transport.request(MCP_METHOD_PING, {}, timeout_seconds=self._discovery_timeout)
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            return BridgeHealth.down(server, str(error))
        return BridgeHealth.up(server)

    async def close(self) -> None:
        """Release every transport this adapter holds."""
        for transport in self._transports.values():
            await transport.close()


__all__ = ["McpAdapter"]
