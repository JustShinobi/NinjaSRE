"""OpenClaw: a capability source, under exactly NinjaSRE's rules.

A source lists the capabilities it offers and runs one on request. That is a
smaller idea than MCP's and it needs no smaller amount of governance: the
classification requirement, the cap, the namespacing, the timeout, and the
guardrail path are the same ones, because they are applied in
``protocols/catalogue.py`` over whatever this adapter returns rather than here.

What this module owns is the document shape and nothing else — which is the
whole argument for the port. Adding a fourth protocol is a file this size.

Optional. A deployment that registers no OpenClaw source constructs no adapter
(FR-020).
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

#: Where a source lists what it offers, and the template for running one.
CAPABILITIES_PATH: Final = "capabilities"
INVOKE_PATH: Final = "capabilities/{name}/invoke"


def capability_from_declaration(declaration: Any, *, server: str) -> BridgedTool:
    """Return the bridged tool one OpenClaw capability declaration describes."""
    if not isinstance(declaration, Mapping):
        raise MalformedServerResponse(
            f"{server} listed a {type(declaration).__name__} where a capability belongs"
        )
    name = declaration.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MalformedServerResponse(f"{server} listed a capability with no usable name")

    description = declaration.get("description")
    schema = declaration.get("parameters") or declaration.get("inputSchema")
    declared = declaration.get("side_effect")
    return BridgedTool(
        server=server,
        tool=name.strip(),
        description=str(description) if isinstance(description, str) else "",
        input_schema=validate_tool_schema(schema, server=server, tool=name.strip()),
        # Kept as a suggestion for the operator's form and used for nothing.
        declared_side_effect=str(declared) if isinstance(declared, str) else "",
    )


class OpenClawAdapter:
    """Every OpenClaw source one team has registered, behind the four-operation port."""

    __slots__ = ("_discovery_timeout", "_invocation_timeout", "_sources")

    def __init__(
        self,
        sources: Mapping[str, PeerTransport],
        *,
        discovery_timeout_seconds: float = PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
        invocation_timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
    ) -> None:
        self._sources = dict(sources)
        self._discovery_timeout = discovery_timeout_seconds
        self._invocation_timeout = invocation_timeout_seconds

    @property
    def kind(self) -> ProtocolKind:
        """Return which wire protocol this adapter speaks."""
        return ProtocolKind.OPENCLAW

    @property
    def servers(self) -> tuple[str, ...]:
        """Return every registered source, in name order."""
        return tuple(sorted(self._sources))

    async def discover(self, server: str) -> Discovery:
        """Return what ``server`` offers, empty when it could not be asked."""
        source = self._sources.get(server)
        if source is None:
            return Discovery(server=server)
        try:
            listed = await source.get_json(
                CAPABILITIES_PATH, timeout_seconds=self._discovery_timeout
            )
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            logger.warning("protocols.openclaw.list_failed", server=server, error=str(error))
            return Discovery(server=server)

        entries = listed.get("capabilities") if isinstance(listed, Mapping) else listed
        if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
            logger.warning("protocols.openclaw.list_malformed", server=server)
            return Discovery(server=server)

        kept: list[BridgedTool] = []
        excluded: list[ExcludedTool] = []
        for entry in entries:
            try:
                declared = capability_from_declaration(entry, server=server)
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
        """Return one capability's declaration, or ``None``."""
        for declared in (await self.discover(server)).tools:
            if declared.tool == tool:
                return declared
        return None

    async def invoke(self, server: str, tool: str, arguments: Mapping[str, Any]) -> BridgedResult:
        """Return what one call produced, classified rather than raised."""
        source = self._sources.get(server)
        if source is None:
            return BridgedResult.failure(
                CapabilityErrorClass.UNAVAILABLE,
                f"{server} is not a source this team has registered",
            )
        try:
            payload = await source.post_json(
                INVOKE_PATH.format(name=tool),
                {"arguments": dict(arguments)},
                timeout_seconds=self._invocation_timeout,
            )
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

        if not isinstance(payload, Mapping) or "result" not in payload:
            return BridgedResult.failure(
                CapabilityErrorClass.UPSTREAM_ERROR,
                f"{server}.{tool} answered in a shape OpenClaw does not define",
                detail="a capability invocation answers an object carrying a result",
            )
        return BridgedResult.ok({"server": server, "capability": tool, "result": payload["result"]})

    async def health(self, server: str) -> BridgeHealth:
        """Return whether ``server`` answers its capability listing."""
        source = self._sources.get(server)
        if source is None:
            return BridgeHealth.down(server, "not registered for this team")
        try:
            await source.get_json(CAPABILITIES_PATH, timeout_seconds=self._discovery_timeout)
        except (ProtocolBridgeError, TimeoutError, OSError) as error:
            return BridgeHealth.down(server, str(error))
        return BridgeHealth.up(server)

    async def close(self) -> None:
        """Release every source transport this adapter holds."""
        for source in self._sources.values():
            await source.close()


def _name_of(entry: Any) -> str:
    """Return the name in ``entry``, or a placeholder, for an exclusion record."""
    if isinstance(entry, Mapping):
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "<unnamed>"


__all__ = [
    "CAPABILITIES_PATH",
    "INVOKE_PATH",
    "OpenClawAdapter",
    "capability_from_declaration",
]
