"""Taking a node out of service, and putting it back."""

from __future__ import annotations

from capabilities.tools.remediation.cordon_drain_node.apply import applier
from capabilities.tools.remediation.cordon_drain_node.read_state import reader
from capabilities.tools.remediation.cordon_drain_node.rollback import generator
from capabilities.tools.remediation.cordon_drain_node.tool import TOOL_NAME, cordon_drain_node
from capabilities.tools.remediation.cordon_drain_node.verify import verifier
from platform.remediation.components import RemediationComponents

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "cordon_drain_node"]
