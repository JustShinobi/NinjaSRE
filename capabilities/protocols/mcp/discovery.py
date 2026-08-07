"""``tools/list`` to a set of declarations this catalogue can hold.

Everything here is reading somebody else's answer without trusting its shape.
The distinction the module keeps is the one from ``protocols/schema.py``: a
declaration that breaks the protocol is **rejected** with an error naming the
entry, and a declaration that is fine but cannot be turned into a provider tool
schema is **excluded** with a recorded reason. Neither breaks the catalogue, and
both are visible to an operator afterwards.

MCP's ``annotations`` are read and kept as the server's *suggestion*. A server
setting ``readOnlyHint`` is telling an operator something worth seeing in the
classification form and telling this code nothing at all — see
``classification.py`` for why that asymmetry is the whole point.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from capabilities.protocols.mcp.client import McpTransport
from capabilities.protocols.port import (
    BridgedTool,
    Discovery,
    ExcludedTool,
    ExclusionReason,
    MalformedServerResponse,
    MalformedToolSchema,
)
from capabilities.protocols.schema import normalisation_failure, validate_tool_schema
from config.constants.protocols import (
    MAX_TOOLS_PER_PROTOCOL_SERVER,
    MCP_METHOD_LIST_TOOLS,
    PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
)
from core.capability.metadata import SideEffectLevel

#: How many ``tools/list`` pages are followed. A cursor that never terminates is
#: a server bug, and an unbounded loop over one is a catalogue build that never
#: finishes — which looks exactly like a hung investigation.
MAX_LIST_PAGES: Final[int] = 20


def suggested_side_effect(annotations: Mapping[str, Any]) -> str:
    """Return what MCP's hints suggest this tool does, as a side-effect level name.

    A suggestion, and never more. ``destructiveHint`` defaults to true in the
    MCP specification for a non-read-only tool, and this follows that reading —
    the conservative direction is the same one Article III takes.
    """
    if annotations.get("readOnlyHint") is True:
        return SideEffectLevel.READ.value
    if annotations.get("destructiveHint") is True:
        return SideEffectLevel.DESTRUCTIVE.value
    if annotations.get("idempotentHint") is True:
        return SideEffectLevel.WRITE_REVERSIBLE.value
    return ""


def tool_from_declaration(declaration: Any, *, server: str) -> BridgedTool:
    """Return the tool ``declaration`` describes, or raise naming what was wrong.

    Raises ``MalformedServerResponse`` when the entry is not a tool declaration
    at all, and ``MalformedToolSchema`` when its input schema is not one.
    """
    if not isinstance(declaration, Mapping):
        raise MalformedServerResponse(
            f"{server} listed a {type(declaration).__name__} where a tool declaration belongs"
        )

    name = declaration.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MalformedServerResponse(
            f"{server} listed a tool with no usable name, so there is nothing the model "
            f"could call it by"
        )

    annotations = declaration.get("annotations")
    hints = annotations if isinstance(annotations, Mapping) else {}
    description = declaration.get("description")
    title = declaration.get("title")

    return BridgedTool(
        server=server,
        tool=name.strip(),
        description=str(description) if isinstance(description, str) else "",
        input_schema=validate_tool_schema(
            declaration.get("inputSchema"), server=server, tool=name.strip()
        ),
        declared_side_effect=suggested_side_effect(hints),
        title=str(title) if isinstance(title, str) else "",
    )


def _entries(result: Any, *, server: str) -> tuple[Sequence[Any], str]:
    """Return one page's tool entries and the cursor that follows it."""
    if not isinstance(result, Mapping):
        raise MalformedServerResponse(
            f"{server} answered {MCP_METHOD_LIST_TOOLS} with a "
            f"{type(result).__name__} where an object belongs"
        )
    tools = result.get("tools")
    if not isinstance(tools, Sequence) or isinstance(tools, str | bytes):
        raise MalformedServerResponse(
            f"{server} answered {MCP_METHOD_LIST_TOOLS} without a list of tools, so its "
            f"catalogue cannot be read"
        )
    cursor = result.get("nextCursor")
    return tools, cursor if isinstance(cursor, str) else ""


async def discovered_tools(
    transport: McpTransport,
    *,
    timeout_seconds: float = PROTOCOL_DISCOVERY_TIMEOUT_SECONDS,
    page_limit: int = MAX_LIST_PAGES,
    tool_limit: int = MAX_TOOLS_PER_PROTOCOL_SERVER,
) -> Discovery:
    """Return what a server offers, with every rejection and exclusion recorded.

    ``tool_limit`` stops the *listing* rather than the catalogue: a server with
    four hundred tools should not cost four hundred pages of discovery on the
    path to every investigation. The cap that decides what reaches the catalogue
    is applied in ``protocols/catalogue.py``, over what this returns, and the
    two are the same number so that neither hides the other's effect.
    """
    server = transport.server
    kept: list[BridgedTool] = []
    excluded: list[ExcludedTool] = []
    offered = 0
    cursor = ""

    for _ in range(page_limit):
        params: dict[str, Any] = {"cursor": cursor} if cursor else {}
        result = await transport.request(
            MCP_METHOD_LIST_TOOLS, params, timeout_seconds=timeout_seconds
        )
        entries, cursor = _entries(result, server=server)

        for entry in entries:
            offered += 1
            try:
                declared = tool_from_declaration(entry, server=server)
            except MalformedToolSchema as error:
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

        if not cursor or offered >= tool_limit + page_limit:
            break

    return Discovery(server=server, tools=tuple(kept), excluded=tuple(excluded), offered=offered)


def _name_of(entry: Any) -> str:
    """Return the name in ``entry``, or a placeholder, for an exclusion record."""
    if isinstance(entry, Mapping):
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "<unnamed>"


__all__ = [
    "MAX_LIST_PAGES",
    "discovered_tools",
    "suggested_side_effect",
    "tool_from_declaration",
]
