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

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "rollback_deployment"]
