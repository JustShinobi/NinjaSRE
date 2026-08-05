"""Getting a structured object out of a model, by whichever route works.

Three mechanisms, tried in order of how much they can be trusted:

1. **Native** structured output, where the provider constrains generation
   against the schema. The result is valid by construction.
2. **Tool coercion**: declare the schema as a single tool and require the model
   to call it. Almost as reliable, and available on every provider that does
   tool calling at all.
3. **Prose parsing**: pull JSON out of whatever the model wrote. Undesirable,
   and necessary — a quantised local model routinely produces near-JSON, and the
   alternative to parsing it is a no-egress deployment that cannot run the
   ``diagnose`` stage.

Which one fired is recorded on the result. That is what turns "the local model
is a bit worse" into a number the evaluation suite can regress on, instead of a
thing people say.
"""

from __future__ import annotations

from core.llm.structured.native import native_request_fields, supports_native
from core.llm.structured.prose_parsing import parse_prose
from core.llm.structured.tool_coercion import (
    STRUCTURED_OUTPUT_TOOL_NAME,
    coercion_tool,
    extract_coerced,
)

__all__ = [
    "STRUCTURED_OUTPUT_TOOL_NAME",
    "coercion_tool",
    "extract_coerced",
    "native_request_fields",
    "parse_prose",
    "supports_native",
]
