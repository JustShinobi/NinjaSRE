"""The envelope, and the one function that is allowed to change it.

``apply_state_updates`` is the single merge path. Not "the recommended way" —
the only way, because every property this feature rests on is a property of
there being exactly one:

- **Stage purity is checkable.** A stage returns updates rather than mutating
  state, so what it wrote is a value somebody can compare against what it
  declared. Two merge paths would mean a second place a write could come from.
- **Slices are replaced, never edited.** A stage that wants to append evidence
  builds the new slice and returns it. That is more typing at the call site and
  it is what makes the merge a function rather than a protocol.
- **The trace is complete.** Every change to state passes through one function,
  so recording what changed is one place rather than a discipline.

``changed_paths`` is the other half. It names what actually moved between two
states, at ``slice.field`` granularity, which is the granularity the ownership
table declares in — "intake writes the investigation slice" would be true of
five stages and would enforce nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from typing import Any

from core.domain.alerts.normalisation import RawAlert
from core.state.slices import (
    AccountingSlice,
    ApprovalSlice,
    ChatSlice,
    EvidenceSlice,
    InvestigationSlice,
    MemorySlice,
)
from core.state.types import SliceName, TeamContext


@dataclass(frozen=True, slots=True)
class AgentState:
    """One investigation's shared state, partitioned by who writes it.

    ``run_id``, ``team``, ``started_at``, and ``raw`` are the envelope rather
    than a slice: they are what the run was started with, nothing writes them,
    and putting them in a slice would mean declaring an owner for a field that
    has none.
    """

    run_id: str
    team: TeamContext = TeamContext()
    raw: RawAlert = RawAlert()
    started_at: datetime = datetime.fromtimestamp(0, tz=UTC)
    chat: ChatSlice = ChatSlice()
    investigation: InvestigationSlice = InvestigationSlice()
    evidence: EvidenceSlice = EvidenceSlice()
    accounting: AccountingSlice = AccountingSlice()
    approvals: ApprovalSlice = ApprovalSlice()
    memory: MemorySlice = MemorySlice()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("state must carry the identifier its run is recorded under")

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of the whole state."""
        return {
            "run_id": self.run_id,
            "team": self.team.to_record(),
            "raw": self.raw.to_record(),
            "started_at": self.started_at.isoformat(),
            "chat": self.chat.to_record(),
            "investigation": self.investigation.to_record(),
            "evidence": self.evidence.to_record(),
            "accounting": self.accounting.to_record(),
            "approvals": self.approvals.to_record(),
            "memory": self.memory.to_record(),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> AgentState:
        """Return the state a stored record describes."""
        return cls(
            run_id=str(record["run_id"]),
            team=TeamContext.from_record(record.get("team") or {}),
            raw=RawAlert.from_record(record.get("raw") or {}),
            started_at=datetime.fromisoformat(str(record["started_at"])),
            chat=ChatSlice.from_record(record.get("chat") or {}),
            investigation=InvestigationSlice.from_record(record.get("investigation") or {}),
            evidence=EvidenceSlice.from_record(record.get("evidence") or {}),
            accounting=AccountingSlice.from_record(record.get("accounting") or {}),
            approvals=ApprovalSlice.from_record(record.get("approvals") or {}),
            memory=MemorySlice.from_record(record.get("memory") or {}),
        )


@dataclass(frozen=True, slots=True)
class StateUpdates:
    """What one stage produced, as whole slices.

    Every field is optional and ``None`` means "no opinion" rather than "clear
    it". A stage that wanted to clear something returns the empty slice, which
    is a thing it had to construct on purpose — and that is the difference
    between a deliberate reset and a forgotten field.
    """

    chat: ChatSlice | None = None
    investigation: InvestigationSlice | None = None
    evidence: EvidenceSlice | None = None
    accounting: AccountingSlice | None = None
    approvals: ApprovalSlice | None = None
    memory: MemorySlice | None = None

    def __bool__(self) -> bool:
        """Return whether this carries any change at all."""
        return bool(self.slices_touched())

    def slices_touched(self) -> frozenset[SliceName]:
        """Return which slices this update replaces."""
        return frozenset(
            SliceName(field.name) for field in fields(self) if getattr(self, field.name) is not None
        )


#: A stage that established nothing returns this rather than ``None``, so the
#: merge has one shape to handle and the lifecycle has no branch for "nothing
#: came back".
NO_UPDATES: StateUpdates = StateUpdates()


def apply_state_updates(state: AgentState, updates: StateUpdates) -> AgentState:
    """Return ``state`` with every slice ``updates`` names replaced.

    The only merge path in the pipeline. Slices are replaced whole rather than
    merged field by field: a field-level merge would let two stages each write
    half of the investigation slice and leave nobody able to say which one
    produced the value that is there.
    """
    changes: dict[str, Any] = {
        name.value: getattr(updates, name.value) for name in updates.slices_touched()
    }
    if not changes:
        return state
    return replace(state, **changes)


def changed_paths(before: AgentState, after: AgentState) -> frozenset[str]:
    """Return the ``slice.field`` paths whose value differs between two states.

    Equality, not identity. A stage that rebuilt a slice and put the same values
    back has written nothing anybody can observe, and reporting it as a write
    would make the purity test fail on a stage that did nothing wrong.
    """
    moved: set[str] = set()
    for name in SliceName:
        old = getattr(before, name.value)
        new = getattr(after, name.value)
        if old == new:
            continue
        for field in fields(old):
            if getattr(old, field.name) != getattr(new, field.name):
                moved.add(f"{name.value}.{field.name}")
    return frozenset(moved)


__all__ = [
    "NO_UPDATES",
    "AgentState",
    "StateUpdates",
    "apply_state_updates",
    "changed_paths",
]
