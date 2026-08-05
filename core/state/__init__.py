"""The shared state one investigation runs over, and the one way to change it.

A stage is a pure ``(state) -> updates`` function and ``apply_state_updates``
is the only thing that merges them. Everything else here is the shape those
values take.
"""

from __future__ import annotations

from core.state.agent_state import (
    NO_UPDATES,
    AgentState,
    StateUpdates,
    apply_state_updates,
    changed_paths,
)
from core.state.catalogue import NO_CAPABILITIES, ResolvedCapabilities
from core.state.evidence import EvidenceEntry, Provenance
from core.state.slices import (
    AccountingSlice,
    ApprovalSlice,
    ChatSlice,
    EvidenceSlice,
    InvestigationSlice,
    MemorySlice,
)
from core.state.types import (
    STAGE_ORDER,
    ApprovalRequest,
    ChatMessage,
    IntakeClassification,
    InvestigationOutcome,
    OutcomeKind,
    SliceName,
    StageName,
    TeamContext,
)

__all__ = [
    "NO_CAPABILITIES",
    "NO_UPDATES",
    "STAGE_ORDER",
    "AccountingSlice",
    "AgentState",
    "ApprovalRequest",
    "ApprovalSlice",
    "ChatMessage",
    "ChatSlice",
    "EvidenceEntry",
    "EvidenceSlice",
    "IntakeClassification",
    "InvestigationOutcome",
    "InvestigationSlice",
    "MemorySlice",
    "OutcomeKind",
    "Provenance",
    "ResolvedCapabilities",
    "SliceName",
    "StageName",
    "StateUpdates",
    "TeamContext",
    "apply_state_updates",
    "changed_paths",
]
