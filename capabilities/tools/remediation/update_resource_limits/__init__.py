"""Changing what a workload may consume, with every prior value recorded."""

from __future__ import annotations

from capabilities.tools.remediation.update_resource_limits.apply import applier
from capabilities.tools.remediation.update_resource_limits.read_state import reader
from capabilities.tools.remediation.update_resource_limits.rollback import generator
from capabilities.tools.remediation.update_resource_limits.tool import (
    TOOL_NAME,
    update_resource_limits,
)
from capabilities.tools.remediation.update_resource_limits.verify import verifier
from platform.remediation.components import RemediationComponents

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "update_resource_limits"]
