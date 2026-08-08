"""Scaling a workload, with the count it was at recorded before it moves."""

from __future__ import annotations

from capabilities.tools.remediation.scale_workload.apply import applier
from capabilities.tools.remediation.scale_workload.read_state import reader
from capabilities.tools.remediation.scale_workload.rollback import generator
from capabilities.tools.remediation.scale_workload.tool import TOOL_NAME, scale_workload
from capabilities.tools.remediation.scale_workload.verify import verifier
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: A scale is verified upward: replicas appearing is the effect, and a count
#: that fell is a scheduler that could not place them. No clearing value,
#: because the target count is the action's own argument rather than a constant
#: — so a scale that moved the count but not far enough reads as effective, and
#: the applier's own verifier is what catches the shortfall against the intent.
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="workload.ready_replicas",
            direction=SignalDirection.UP,
        ),
    ),
    # Long enough for a scheduler to place new instances and for them to pass a
    # readiness probe.
    settle_seconds=300,
)

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
    verification=verification,
)

__all__ = ["TOOL_NAME", "components", "verification", "scale_workload"]
