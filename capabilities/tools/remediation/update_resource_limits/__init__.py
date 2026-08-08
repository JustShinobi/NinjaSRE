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
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: Raising a memory limit has worked when the workload stops being killed for
#: exceeding it. Zero is the clearing value, and it is the honest one: one OOM
#: kill after the change is the change not having been enough.
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="workload.oom_kills_per_hour",
            direction=SignalDirection.DOWN,
            clears_at=0.0,
        ),
    ),
    # A limit change restarts the workload, so this waits for the new instances
    # to be under load rather than merely running.
    settle_seconds=600,
)

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
    verification=verification,
)

__all__ = ["TOOL_NAME", "components", "verification", "update_resource_limits"]
