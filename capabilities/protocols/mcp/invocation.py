"""``tools/call`` to a result, and the one rule about what comes back.

**A server's output is data.** Not a prompt fragment, not an instruction, not
something this module reads for directives about what to do next. It is put in a
``value`` and handed to the capability layer, which puts it in a tool result the
model reads exactly as it reads a native tool's answer — through the guardrail
engine's ``post_tool_use`` scan on the way (FR-010).

There is nothing clever to do about a server that returns "ignore your previous
instructions". Stripping it would be a filter somebody eventually gets around;
what actually holds is that no code path here treats content as anything but a
string, no hook is registered from it, no system prompt is amended by it, and no
tool call is created from it — a hook may not inject calls at all, by design in
``core/agent/hooks``. SC-005 asserts that end to end.

Failure is a value here too. A server that refuses, times out, or answers
nonsense produces a classified ``BridgedResult`` and never an exception, because
one bridged server having a bad day must cost one call rather than the turn.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from capabilities.protocols.mcp.client import JsonRpcFailure, McpTransport
from capabilities.protocols.port import BridgedResult, MalformedServerResponse
from config.constants.protocols import (
    MAX_PROTOCOL_RESULT_BYTES,
    MCP_METHOD_CALL_TOOL,
    PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
)
from core.capability.result import CapabilityErrorClass

#: Content blocks this bridge can render as text. Anything else is kept as its
#: declared type and a note, rather than dropped: a tool answering with an image
#: has answered, and reporting nothing would read as a tool that did not run.
TEXT_BLOCK = "text"


def read_content(payload: Any, *, server: str, tool: str) -> tuple[Any, bool]:
    """Return one ``tools/call`` answer as data, and whether it was truncated.

    Raises ``MalformedServerResponse`` when the answer is not the shape the
    protocol defines — which is a specific, actionable failure rather than a
    ``KeyError`` three frames up the stack.
    """
    if not isinstance(payload, Mapping):
        raise MalformedServerResponse(
            f"{server}.{tool} answered with a {type(payload).__name__} where a "
            f"{MCP_METHOD_CALL_TOOL} result belongs"
        )

    blocks = payload.get("content")
    structured = payload.get("structuredContent")
    if blocks is None and structured is None:
        raise MalformedServerResponse(
            f"{server}.{tool} answered with neither content nor structuredContent, so "
            f"there is nothing to record as evidence"
        )
    if blocks is not None and (not isinstance(blocks, Sequence) or isinstance(blocks, str | bytes)):
        raise MalformedServerResponse(
            f"{server}.{tool} answered with content that is a "
            f"{type(blocks).__name__} rather than a list of content blocks"
        )

    rendered: list[Any] = []
    for block in blocks or ():
        if not isinstance(block, Mapping):
            raise MalformedServerResponse(
                f"{server}.{tool} answered with a {type(block).__name__} where a content "
                f"block belongs"
            )
        kind = block.get("type")
        if kind == TEXT_BLOCK and isinstance(block.get("text"), str):
            rendered.append(block["text"])
        else:
            rendered.append({"type": kind, "summary": f"a {kind} block this bridge does not read"})

    text = "\n".join(item for item in rendered if isinstance(item, str))
    truncated = len(text.encode("utf-8")) > MAX_PROTOCOL_RESULT_BYTES
    if truncated:
        text = text.encode("utf-8")[:MAX_PROTOCOL_RESULT_BYTES].decode("utf-8", errors="ignore")

    value: dict[str, Any] = {"server": server, "tool": tool}
    if text:
        value["text"] = text
    other = [item for item in rendered if not isinstance(item, str)]
    if other:
        value["blocks"] = other
    if structured is not None:
        value["structured"] = structured
    return value, truncated


async def invoke_tool(
    transport: McpTransport,
    *,
    tool: str,
    arguments: Mapping[str, Any],
    timeout_seconds: float = PROTOCOL_INVOCATION_TIMEOUT_SECONDS,
) -> BridgedResult:
    """Return what one ``tools/call`` produced, classified rather than raised."""
    server = transport.server
    started = time.perf_counter()

    try:
        payload = await transport.request(
            MCP_METHOD_CALL_TOOL,
            {"name": tool, "arguments": dict(arguments)},
            timeout_seconds=timeout_seconds,
        )
    except TimeoutError:
        return BridgedResult.failure(
            CapabilityErrorClass.TIMEOUT,
            f"{server}.{tool} did not answer within {timeout_seconds:g}s",
            duration_seconds=time.perf_counter() - started,
        )
    except JsonRpcFailure as error:
        return BridgedResult.failure(
            CapabilityErrorClass.UPSTREAM_ERROR,
            f"{server}.{tool} was refused by the server",
            detail=error.detail,
            duration_seconds=time.perf_counter() - started,
        )
    except MalformedServerResponse as error:
        return BridgedResult.failure(
            CapabilityErrorClass.UPSTREAM_ERROR,
            f"{server}.{tool} answered in a shape MCP does not define",
            detail=str(error),
            duration_seconds=time.perf_counter() - started,
        )

    elapsed = time.perf_counter() - started

    try:
        value, truncated = read_content(payload, server=server, tool=tool)
    except MalformedServerResponse as error:
        return BridgedResult.failure(
            CapabilityErrorClass.UPSTREAM_ERROR,
            f"{server}.{tool} answered in a shape MCP does not define",
            detail=str(error),
            duration_seconds=elapsed,
        )

    if isinstance(payload, Mapping) and payload.get("isError") is True:
        return BridgedResult.failure(
            CapabilityErrorClass.UPSTREAM_ERROR,
            f"{server}.{tool} reported a tool error",
            detail=str(value.get("text", "")),
            duration_seconds=elapsed,
        )

    return BridgedResult.ok(value, truncated=truncated, duration_seconds=elapsed)


__all__ = [
    "TEXT_BLOCK",
    "invoke_tool",
    "read_content",
]
