"""Restarting a workload: read the instances, replace them, verify they changed.

The one capability in the set whose rollback is not a reversal. What it
records instead is the recovery — and the recording is the point, because an
action whose undo is "there is none" has to say so where somebody will read
it rather than leave it to be discovered.
"""

from __future__ import annotations

from capabilities.tools.remediation.restart_workload.apply import applier
from capabilities.tools.remediation.restart_workload.read_state import reader
from capabilities.tools.remediation.restart_workload.rollback import generator
from capabilities.tools.remediation.restart_workload.tool import TOOL_NAME, restart_workload
from capabilities.tools.remediation.restart_workload.verify import verifier
from platform.remediation.components import RemediationComponents

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "restart_workload"]
