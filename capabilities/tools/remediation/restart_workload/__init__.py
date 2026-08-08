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
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: A restart is verified by the thing that made it necessary settling, not by
#: the pods having changed — the applier's own verifier already checks that the
#: instances are new, and "the instances are new" is not "the problem is gone".
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="workload.restarts_per_hour",
            direction=SignalDirection.DOWN,
            # One restart an hour is the deployment's own doing; more than that
            # is the workload failing again.
            clears_at=1.0,
        ),
    ),
    # Long enough for a crash-looping workload to fail again if it is going to.
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

__all__ = ["TOOL_NAME", "components", "verification", "restart_workload"]
