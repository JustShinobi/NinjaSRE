"""The proposal capability and its binding to a review queue.

Two modules rather than three: there is nothing to shape. The capability returns
a receipt saying the proposal is queued and explicitly not part of the knowledge
base, and a receipt with a rendering layer would be a receipt somebody could
render into something that sounded like a document.
"""

from __future__ import annotations

from capabilities.tools.system.knowledge_propose.tool import TOOL_NAME, propose_knowledge

__all__ = ["TOOL_NAME", "propose_knowledge"]
