"""Rolling a deployment back, and recording what it was on so that is reversible."""

from __future__ import annotations

from capabilities.tools.remediation.rollback_deployment.apply import applier
from capabilities.tools.remediation.rollback_deployment.read_state import reader
from capabilities.tools.remediation.rollback_deployment.rollback import generator
from capabilities.tools.remediation.rollback_deployment.tool import (
    TOOL_NAME,
    rollback_deployment,
)
from capabilities.tools.remediation.rollback_deployment.verify import verifier
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: A release rolled back has worked when the errors it introduced stop. The
#: clearing value is the rate a healthy deployment sits at rather than zero,
#: because no production service has an error rate of exactly nothing.
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="workload.error_rate",
            direction=SignalDirection.DOWN,
            clears_at=1.0,
        ),
    ),
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

__all__ = ["TOOL_NAME", "components", "verification", "rollback_deployment"]
