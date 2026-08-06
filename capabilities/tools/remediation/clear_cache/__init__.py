"""Clearing a cache: the action that exercises the no-derivable-plan path.

Shipped on purpose. Every other capability here produces a plan, and a
waiver path that only the untestable capabilities used would be one nobody
had ever run.
"""

from __future__ import annotations

from capabilities.tools.remediation.clear_cache.apply import applier
from capabilities.tools.remediation.clear_cache.read_state import reader
from capabilities.tools.remediation.clear_cache.rollback import generator
from capabilities.tools.remediation.clear_cache.tool import TOOL_NAME, clear_cache
from capabilities.tools.remediation.clear_cache.verify import verifier
from platform.remediation.components import RemediationComponents

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "clear_cache"]
