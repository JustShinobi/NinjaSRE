"""One renderer per change type, and the registry that binds them.

The registry is complete by construction: it names every member of
``ChangeType``, so a sixth change type added without a renderer fails when this
module is imported rather than when somebody opens the review for it — which
would be during whatever made them propose the change.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from platform.approvals.diff.engine import DiffRenderer
from platform.approvals.diff.renderers.capability import CapabilityRenderer
from platform.approvals.diff.renderers.config import ConfigurationRenderer
from platform.approvals.diff.renderers.knowledge import KnowledgeRenderer
from platform.approvals.diff.renderers.prompt import PromptRenderer
from platform.approvals.diff.renderers.remediation import RemediationRenderer
from platform.approvals.models import ChangeType

RENDERERS: Final[Mapping[ChangeType, DiffRenderer]] = {
    ChangeType.CONFIGURATION: ConfigurationRenderer(),
    ChangeType.PROMPT: PromptRenderer(),
    ChangeType.CAPABILITY: CapabilityRenderer(),
    ChangeType.KNOWLEDGE: KnowledgeRenderer(),
    ChangeType.REMEDIATION: RemediationRenderer(),
}

_missing = set(ChangeType) - set(RENDERERS)
if _missing:  # pragma: no cover — a build with an unrendered change type cannot start
    raise RuntimeError(
        f"No diff renderer for {', '.join(sorted(kind.value for kind in _missing))}. "
        f"A change type nobody can review is one that gets approved unread."
    )


__all__ = [
    "RENDERERS",
    "CapabilityRenderer",
    "ConfigurationRenderer",
    "KnowledgeRenderer",
    "PromptRenderer",
    "RemediationRenderer",
]
