"""Changing a flag, with both its value and its rollout recorded first."""

from __future__ import annotations

from capabilities.tools.remediation.toggle_feature_flag.apply import applier
from capabilities.tools.remediation.toggle_feature_flag.read_state import reader
from capabilities.tools.remediation.toggle_feature_flag.rollback import generator
from capabilities.tools.remediation.toggle_feature_flag.tool import (
    TOOL_NAME,
    toggle_feature_flag,
)
from capabilities.tools.remediation.toggle_feature_flag.verify import verifier
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import VerificationDeclaration

#: The one capability in the shipped set with no verifiable effect, and it is
#: here on purpose: FR-006's unverifiable path is exercised by the catalogue
#: rather than being a branch nobody has run.
verification = VerificationDeclaration.unverifiable(
    "a feature flag's effect appears in whatever the flag guards, which differs "
    "per flag and is not something this capability can name. Whether an "
    "unverifiable action may run unattended is a policy decision, not a default."
)

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
    verification=verification,
)

__all__ = ["TOOL_NAME", "components", "verification", "toggle_feature_flag"]
