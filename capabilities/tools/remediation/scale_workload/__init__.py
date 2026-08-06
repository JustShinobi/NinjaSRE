"""Scaling a workload, with the count it was at recorded before it moves."""

from __future__ import annotations

from capabilities.tools.remediation.scale_workload.apply import applier
from capabilities.tools.remediation.scale_workload.read_state import reader
from capabilities.tools.remediation.scale_workload.rollback import generator
from capabilities.tools.remediation.scale_workload.tool import TOOL_NAME, scale_workload
from capabilities.tools.remediation.scale_workload.verify import verifier
from platform.remediation.components import RemediationComponents

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "scale_workload"]
