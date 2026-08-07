"""ACP: another agent's declared skills, under exactly NinjaSRE's rules.

Agent-to-agent rather than agent-to-tool, which changes the vocabulary and
nothing else. A peer lists the agents it runs; each becomes a bridged capability
named ``<peer>__<agent>``; invoking one posts a run and reads its output. The
classification requirement applies unchanged, and it matters more here than it
does for MCP: an agent on the other end decides for itself what to do with an
input, so "what does this do to the world" is a question its author cannot
answer for every call and its operator must answer once.

Optional. A deployment that registers no ACP peer constructs no adapter and this
module is imported by nothing at runtime (FR-020).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from capabilities.protocols.peer import PeerTransport
from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ExcludedTool,
    ExclusionReason,
    MalformedServerResponse,
    MalformedToolSchema,
    ProtocolBridgeError,
    ProtocolKind,
)
from capabilities.protocols.schema import normalisation_failure, validate_tool_schema
from config.constants.protocols import (
    PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
    PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
)
from core.capability.result import CapabilityErrorClass
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Where a peer lists the agents it runs, and where a run is posted.
AGENTS_PATH: Final = "agents"
RUNS_PATH: Final = "runs"


def agent_from_declaration(declaration: Any, *, server: str) -> BridgedTool:
    """Return the bridged tool one ACP agent declaration describes."""
    if not isinstance(declaration, Mapping):
        raise MalformedServerResponse(
            f"{server} listed a {type(declaration).__name__} where an agent belongs"
        )
    name = declaration.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MalformedServerResponse(f"{server} listed an agent with no usable name")

    description = declaration.get("description")
    schema = declaration.get("input") or declaration.get("inputSchema")
    return BridgedTool(
        server=server,
        tool=name.strip(),
        description=str(description) if isinstance(description, str) else "",
        input_schema=validate_tool_schema(schema, server=server, tool=name.strip()),
        # An ACP peer declares no side effect at all, which is the honest
        # answer for an agent and the reason operator classification is not
        # negotiable here.
        declared_side_effect="",
    )


def _read_output(payload: Any, *, server: str, agent: str) -> dict[str, Any]:
    """Return one run's output as data, or raise naming the shape that arrived."""
    if not isinstance(payload, Mapping):
        raise MalformedServerResponse(
            f"{server}.{agent} answered with a {type(payload).__name__} where a run belongs"
        )
    output = payload.get("output")
    if output is None:
        raise MalformedServerResponse(
            f"{server}.{agent} answered a run with no output, so there is nothing to record"
        )
    value: dict[str, Any] = {"server": server, "agent": agent, "output": output}
    status = payload.get("status")
    if isinstance(status, str):
        value["status"] = status
    return value


class AcpAdapter:
    """Every ACP peer one team has registered, behind the four-operation port."""

    __slots__ = ("_discovery_timeout", "_invocation_timeout", "_peers")

    def __init__(
        self,
        peers: Mapping[str, PeerTransport],
        *,
        discovery_timeout_seconds: float = PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
        invocation_timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> None:
        self._peers = dict(peers)
        self._discovery_timeout = discovery_timeout_seconds
        self._invocation_timeout = invocation_timeout_seconds

    @property
    def kind(self) -> ProtocolKind:
        """Return which wire protocol this adapter speaks."""
        return ProtocolKind.ACP

    @property
    def servers(self) -> tuple[str, ...]:
        """Return every registered peer, in name order."""
        return tuple(sorted(self._peers))

    async def discover(self, server: str) -> Discovery:
        """Return the agents ``server`` runs, empty when it could not be asked."""
        peer = self._peers.get(server)
        if peer is None:
            return Discovery(server=server)
        try:
            listed = await peer.get_json(AGENTS_PATH, timeout_seconds=self._discovery_timeout)
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            logger.warning("protocols.acp.list_failed", server=server, error=str(error))
            return Discovery(server=server)

        entries = listed.get("agents") if isinstance(listed, Mapping) else listed
        if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
            logger.warning("protocols.acp.list_malformed", server=server)
            return Discovery(server=server)

        kept: list[BridgedTool] = []
        excluded: list[ExcludedTool] = []
        for entry in entries:
            try:
                declared = agent_from_declaration(entry, server=server)
            except (MalformedServerResponse, MalformedToolSchema) as error:
                excluded.append(
                    ExcludedTool(
                        server=server,
                        tool=_name_of(entry),
                        reason=ExclusionReason.MALFORMED_SCHEMA,
                        detail=str(error),
                    )
                )
                continue
            failure = normalisation_failure(declared.input_schema)
            if failure is not None:
                excluded.append(
                    ExcludedTool(
                        server=server,
                        tool=declared.tool,
                        reason=ExclusionReason.UNNORMALISABLE_SCHEMA,
                        detail=failure,
                    )
                )
                continue
            kept.append(declared)

        return Discovery(
            server=server, tools=tuple(kept), excluded=tuple(excluded), offered=len(entries)
        )

    async def describe(self, server: str, tool: str) -> BridgedTool | None:
        """Return one agent's declaration, or ``None``."""
        for declared in (await self.discover(server)).tools:
            if declared.tool == tool:
                return declared
        return None

    async def invoke(self, server: str, tool: str, arguments: Mapping[str, Any]) -> BridgedResult:
        """Return what one run produced, classified rather than raised."""
        peer = self._peers.get(server)
        if peer is None:
            return BridgedResult.failure(
                CapabilityErrorClass.UNAVAILABLE,
                f"{server} is not a peer this team has registered",
            )
        try:
            payload = await peer.post_json(
                RUNS_PATH,
                {"agent_name": tool, "input": dict(arguments)},
                timeout_seconds=self._invocation_timeout,
            )
            return BridgedResult.ok(_read_output(payload, server=server, agent=tool))
        except TimeoutError:
            return BridgedResult.failure(
                CapabilityErrorClass.TIMEOUT,
                f"{server}.{tool} did not answer within {self._invocation_timeout:g}s",
            )
        except (ProtocolBridgeError, OSError) as error:
            return BridgedResult.failure(
                CapabilityErrorClass.UPSTREAM_ERROR,
                f"{server}.{tool} did not complete",
                detail=str(error),
            )

    async def health(self, server: str) -> BridgeHealth:
        """Return whether ``server`` answers its agent listing."""
        peer = self._peers.get(server)
        if peer is None:
            return BridgeHealth.down(server, "not registered for this team")
        try:
            await peer.get_json(AGENTS_PATH, timeout_seconds=self._discovery_timeout)
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            return BridgeHealth.down(server, str(error))
        return BridgeHealth.up(server)

    async def close(self) -> None:
        """Release every peer transport this adapter holds."""
        for peer in self._peers.values():
            await peer.close()


def _name_of(entry: Any) -> str:
    """Return the name in ``entry``, or a placeholder, for an exclusion record."""
    if isinstance(entry, Mapping):
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "<unnamed>"


__all__ = ["AGENTS_PATH", "RUNS_PATH", "AcpAdapter", "agent_from_declaration"]
