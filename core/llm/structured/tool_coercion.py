"""Structured output by making the schema the only tool the model may call.

The fallback when a provider has no native JSON mode but does have tool calling
— Bedrock's Converse API, most NIM and Ollama models. The model's arguments to
that one tool *are* the structured result, and they arrive already parsed by the
provider's own tool-call machinery, which is the whole reason this ranks above
reading prose.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.llm.types import ToolCall, ToolSchema

#: Distinct enough that no capability will ever be called this, and stable so a
#: trace of a coerced call reads the same across providers.
STRUCTURED_OUTPUT_TOOL_NAME = "ninjasre_emit_structured_result"

_TOOL_DESCRIPTION = (
    "Return the final answer. Call this exactly once, with the answer supplied "
    "as this tool's arguments. Do not answer in prose."
)


def coercion_tool(schema: Mapping[str, Any]) -> ToolSchema:
    """Return the single tool that stands in for a structured-output request."""
    return ToolSchema(
        name=STRUCTURED_OUTPUT_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=schema,
    )


def extract_coerced(tool_calls: Sequence[ToolCall]) -> Mapping[str, Any] | None:
    """Return the arguments of the coercion call, or ``None`` if it never came.

    A model asked for one tool sometimes calls it more than once. The first call
    wins: it is the one the model committed to before it started second-guessing,
    and picking it is at least deterministic, which a "best" heuristic would not
    be.
    """
    for call in tool_calls:
        if call.name == STRUCTURED_OUTPUT_TOOL_NAME:
            return dict(call.arguments)
    return None


def strip_coercion_calls(tool_calls: Sequence[ToolCall]) -> tuple[ToolCall, ...]:
    """Return ``tool_calls`` without the coercion call.

    The coercion tool is NinjaSRE's own scaffolding. Leaving it in the result
    would offer the runtime a tool to execute that does not exist.
    """
    return tuple(call for call in tool_calls if call.name != STRUCTURED_OUTPUT_TOOL_NAME)


__all__ = [
    "STRUCTURED_OUTPUT_TOOL_NAME",
    "coercion_tool",
    "extract_coerced",
    "strip_coercion_calls",
]
