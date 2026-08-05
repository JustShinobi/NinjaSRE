"""One observation, with everything needed to check it and to price it.

There are two evidence types in NinjaSRE and the difference between them is the
point of this one. The runtime's entry is what a loop holds while it is
running: enough to put in the next prompt and to evict when the context budget
is tight. This entry is what the *investigation* holds, and it answers a
different question — can somebody who was not there establish that this
observation happened?

That question needs three fields the runtime's does not carry:

``arguments``
    What the capability was actually called with. "The error rate was 12%" is
    unfalsifiable without the query that produced it.

``recorded_at``
    When the observation was made, as an absolute instant. An iteration number
    orders evidence within one run and says nothing across two.

``provenance``
    Which run, which turn, which sub-agent. A claim resting on "a specialist
    told me" is a materially different claim from one resting on "I read it",
    and a report that cannot tell them apart is overstating what it knows.

The value hints the budget policy reads — ``cited``, ``truncated``, and the
token cost — come across from the runtime entry unchanged, so evidence promoted
into the investigation can still be evicted on the same value function.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from core.agent.session import EvidenceEntry as RuntimeEvidenceEntry
from core.capability.metadata import EvidenceType
from core.capability.result import Evidence
from core.capability.tokens import estimate_tokens
from core.state.types import StageName


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where one observation came from, precisely enough to go back to it."""

    stage: StageName = StageName.GATHER_EVIDENCE
    runtime: str = ""
    session_id: str = ""
    call_id: str = ""
    iteration: int = 0
    origin: str = ""

    @property
    def from_subagent(self) -> bool:
        """Return whether a specialist reported this rather than the loop observing it."""
        return bool(self.origin)

    def describe(self) -> str:
        """Return one sentence naming where this came from."""
        who = f"the {self.origin} specialist" if self.origin else "the investigation loop"
        where = (
            f" (session {self.session_id}, iteration {self.iteration})" if self.session_id else ""
        )
        return f"observed by {who} during {self.stage.value}{where}"

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this provenance."""
        return {
            "stage": self.stage.value,
            "runtime": self.runtime,
            "session_id": self.session_id,
            "call_id": self.call_id,
            "iteration": self.iteration,
            "origin": self.origin,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Provenance:
        """Return the provenance a stored record describes."""
        return cls(
            stage=StageName(record.get("stage", StageName.GATHER_EVIDENCE.value)),
            runtime=str(record.get("runtime", "")),
            session_id=str(record.get("session_id", "")),
            call_id=str(record.get("call_id", "")),
            iteration=int(record.get("iteration", 0)),
            origin=str(record.get("origin", "")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """One observation the investigation holds."""

    id: str
    capability: str
    source: str
    evidence_type: EvidenceType
    summary: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    payload: str = ""
    reference: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    provenance: Provenance = Provenance()
    cited: bool = False
    truncated: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("an evidence entry must carry an identifier a claim can cite")
        if not self.capability.strip():
            raise ValueError(
                f"{self.id}: an evidence entry must name the capability that produced it"
            )

    @property
    def tokens(self) -> int:
        """Return what this entry costs in a prompt, summary and payload together."""
        return estimate_tokens(f"{self.summary}\n{self.payload}")

    def as_evidence(self) -> Evidence:
        """Return the capability-layer shape, for a conclusion that cites this."""
        return Evidence(
            source=self.source,
            evidence_type=self.evidence_type,
            summary=self.summary,
            reference=self.reference,
        )

    def cite(self) -> EvidenceEntry:
        """Return this entry marked as reasoned from."""
        return replace(self, cited=True)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this entry."""
        return {
            "id": self.id,
            "capability": self.capability,
            "source": self.source,
            "evidence_type": self.evidence_type.value,
            "summary": self.summary,
            "arguments": dict(self.arguments),
            "payload": self.payload,
            "reference": self.reference,
            "recorded_at": self.recorded_at.isoformat(),
            "provenance": self.provenance.to_record(),
            "cited": self.cited,
            "truncated": self.truncated,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EvidenceEntry:
        """Return the entry a stored record describes."""
        return cls(
            id=str(record["id"]),
            capability=str(record["capability"]),
            source=str(record.get("source", "")),
            evidence_type=EvidenceType(record["evidence_type"]),
            summary=str(record.get("summary", "")),
            arguments=dict(record.get("arguments") or {}),
            payload=str(record.get("payload", "")),
            reference=str(record.get("reference", "")),
            recorded_at=datetime.fromisoformat(str(record["recorded_at"])),
            provenance=Provenance.from_record(record.get("provenance") or {}),
            cited=bool(record.get("cited", False)),
            truncated=bool(record.get("truncated", False)),
        )

    @classmethod
    def from_runtime(
        cls,
        entry: RuntimeEvidenceEntry,
        *,
        provenance: Provenance,
        arguments: Mapping[str, Any] | None = None,
        recorded_at: datetime | None = None,
    ) -> EvidenceEntry:
        """Return the investigation-level entry a runtime observation becomes.

        The identifier is carried across unchanged. Renumbering here would break
        every citation the conclusion already made against it, which is the one
        thing the diagnosis stage is about to check.
        """
        return cls(
            id=entry.id,
            capability=entry.capability,
            source=entry.source,
            evidence_type=entry.evidence_type,
            summary=entry.summary,
            arguments=dict(arguments or {}),
            payload=entry.content,
            reference=entry.reference,
            recorded_at=recorded_at if recorded_at is not None else datetime.now(UTC),
            provenance=replace(
                provenance,
                call_id=entry.call_id or provenance.call_id,
                iteration=entry.iteration or provenance.iteration,
                origin=entry.origin or provenance.origin,
            ),
            cited=entry.cited,
            truncated=entry.truncated,
        )


__all__ = [
    "EvidenceEntry",
    "Provenance",
]
