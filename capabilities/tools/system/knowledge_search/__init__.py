"""The knowledge-base capability, its result shaping, and its binding.

Split the same way as the other two system capabilities: the declaration for a
reviewer, the shaping for whoever argues about what the model reads, and the
binding for the composition root.
"""

from __future__ import annotations

from capabilities.tools.system.knowledge_search.tool import TOOL_NAME, search_knowledge_base

__all__ = ["TOOL_NAME", "search_knowledge_base"]
