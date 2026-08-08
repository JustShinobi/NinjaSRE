"""Clearing a cache: the action that exercises the no-derivable-plan path.

Shipped on purpose. Every other capability here produces a plan, and a
waiver path that only the untestable capabilities used would be one nobody
had ever run.
"""

from __future__ import annotations

from capabilities.tools.remediation.clear_cache.apply import applier
from capabilities.tools.remediation.clear_cache.read_state import reader
from capabilities.tools.remediation.clear_cache.rollback import generator
from capabilities.tools.remediation.clear_cache.tool import TOOL_NAME, clear_cache
from capabilities.tools.remediation.clear_cache.verify import verifier
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)

#: Clearing reclaimable space shows up in one number and nothing else, and the
#: detector that asks for it has a clearing threshold — so this is the one
#: capability that can distinguish "it did not work" from "cannot tell".
verification = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name="filesystem.used_percent",
            direction=SignalDirection.DOWN,
            # The value at which a near-full detector stops firing. Below it the
            # condition the action was taken against no longer holds, which is
            # the only thing this feature calls success.
            clears_at=80.0,
        ),
    ),
    # A reclaim is visible as soon as the filesystem is next sampled, and every
    # source in the shipped set samples at least once a minute.
    settle_seconds=180,
)

components = RemediationComponents(
    capability=TOOL_NAME,
    reader=reader,
    applier=applier,
    generator=generator,
    verifier=verifier,
    verification=verification,
)

__all__ = ["TOOL_NAME", "components", "verification", "clear_cache"]
