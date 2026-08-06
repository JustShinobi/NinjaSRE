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

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
)

__all__ = ["TOOL_NAME", "components", "toggle_feature_flag"]
