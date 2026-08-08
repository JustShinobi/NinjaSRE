"""Taking a node out of service, and putting it back."""

from __future__ import annotations

from capabilities.tools.remediation.cordon_drain_node.apply import applier
from capabilities.tools.remediation.cordon_drain_node.read_state import reader
from capabilities.tools.remediation.cordon_drain_node.rollback import generator
from capabilities.tools.remediation.cordon_drain_node.tool import TOOL_NAME, cordon_drain_node
from capabilities.tools.remediation.cordon_drain_node.verify import verifier
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: A drain has worked when nothing is left running on the node. Zero is the
#: clearing value, which makes a half-finished drain ``ineffective`` rather than
#: an ambiguous partial success.
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="node.workload_count",
            direction=SignalDirection.DOWN,
            clears_at=0.0,
        ),
    ),
    # Evictions are paced by whatever disruption budgets the workloads declare,
    # so this is the longest settle period in the shipped set.
    settle_seconds=900,
)

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
    verification=verification,
)

__all__ = ["TOOL_NAME", "components", "verification", "cordon_drain_node"]
