"""The vocabulary the pipeline's state is written in.

Stage names, slice names, the team a run belongs to, and the two verdicts that
decide whether the run continues. They are here rather than in the modules that
produce them because state has to name them and a stage has to produce them,
and the alternative is a cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from config.constants.investigation import DEFAULT_TOOL_BUDGET


class StageName(StrEnum):
    """The six stages, named as the trace records them."""

    RESOLVE_INTEGRATIONS = "resolve_integrations"
    INTAKE = "intake"
    PLAN_EVIDENCE = "plan_evidence"
    GATHER_EVIDENCE = "gather_evidence"
    DIAGNOSE = "diagnose"
    DELIVER = "deliver"


#: The order the pipeline runs them in. Sequential by design: concurrency lives
#: inside ``gather_evidence``, where it is bounded, and a well-defined stage
#: order is what makes one run's trajectory comparable to another's.
STAGE_ORDER: Final[tuple[StageName, ...]] = (
    StageName.RESOLVE_INTEGRATIONS,
    StageName.INTAKE,
    StageName.PLAN_EVIDENCE,
    StageName.GATHER_EVIDENCE,
    StageName.DIAGNOSE,
    StageName.DELIVER,
)


class SliceName(StrEnum):
    """The six concerns state is partitioned into."""

    CHAT = "chat"
    INVESTIGATION = "investigation"
    EVIDENCE = "evidence"
    ACCOUNTING = "accounting"
    APPROVALS = "approvals"
    MEMORY = "memory"


class OutcomeKind(StrEnum):
    """How an investigation ended.

    The first three end it early and the last two end it having run. That
    distinction is what the lifecycle branches on, and it is a property of the
    kind rather than a flag a stage remembers to set.
    """

    NOISE = "noise"
    DUPLICATE = "duplicate"
    NO_INTEGRATIONS = "no_integrations"
    DIAGNOSED = "diagnosed"
    FAILED = "failed"

    @property
    def halts(self) -> bool:
        """Return whether reaching this outcome stops the remaining stages."""
        return self in _HALTING_OUTCOMES


_HALTING_OUTCOMES: Final[frozenset[OutcomeKind]] = frozenset(
    {OutcomeKind.NOISE, OutcomeKind.DUPLICATE, OutcomeKind.NO_INTEGRATIONS}
)


@dataclass(frozen=True, slots=True)
class InvestigationOutcome:
    """Why the run ended, in terms an operator can act on.

    ``next_steps`` is what makes the zero-integration path a useful answer
    rather than an empty report: "connect Datadog or Loki, either of which
    would have served this alert" is something somebody can do in a minute.
    """

    kind: OutcomeKind
    headline: str = ""
    detail: str = ""
    next_steps: tuple[str, ...] = ()

    @property
    def halts(self) -> bool:
        """Return whether this outcome stops the remaining stages."""
        return self.kind.halts

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this outcome."""
        return {
            "kind": self.kind.value,
            "headline": self.headline,
            "detail": self.detail,
            "next_steps": list(self.next_steps),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> InvestigationOutcome:
        """Return the outcome a stored record describes."""
        return cls(
            kind=OutcomeKind(record["kind"]),
            headline=str(record.get("headline", "")),
            detail=str(record.get("detail", "")),
            next_steps=tuple(str(item) for item in record.get("next_steps") or ()),
        )


@dataclass(frozen=True, slots=True)
class IntakeClassification:
    """Intake's verdict on whether there is anything to investigate.

    The confidence is recorded whichever way the verdict went. A false negative
    — a real incident called noise — is the expensive mistake, and it is only
    auditable if the run wrote down how sure it was at the moment it stopped.
    """

    is_incident: bool = True
    confidence: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this classification."""
        return {
            "is_incident": self.is_incident,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> IntakeClassification:
        """Return the classification a stored record describes."""
        return cls(
            is_incident=bool(record.get("is_incident", True)),
            confidence=float(record.get("confidence", 0.0)),
            reason=str(record.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class TeamContext:
    """Who this run is for, who caused it, and what they have.

    Everything a stage needs about the deployment that is not a capability and
    not a secret. Hierarchical configuration resolves it; the pipeline only
    reads it.

    ``actor_id`` and ``actor_kind`` are what make a tool call attributable. They
    ride here rather than in a slice or a second parameter because this is the
    one value every stage already holds — an attribution that had to be threaded
    separately is one that gets dropped on whichever path nobody remembered, and
    the path it is dropped on is the one somebody will ask about. The state
    serialises this whole context, so the trace records who caused the run
    without anything else having to remember to.

    They are plain strings rather than the identity layer's ``Principal``
    because `core/` describes what an investigation *is* and does not need to
    know how somebody signed in. A transport fills them from the principal it
    authenticated: ``actor_id=principal.principal_id`` and
    ``actor_kind=principal.actor_kind.value``.

    Empty is a real answer, and the honest one: a run nothing human started —
    a scheduled sweep, a replayed fixture — has no principal, and a trace that
    invented one would be worse than a trace that says so.
    """

    team_id: str = ""
    integrations: tuple[str, ...] = ()
    sandbox_profiles: tuple[str, ...] = ()
    destinations: tuple[str, ...] = ()
    tool_budget: int = DEFAULT_TOOL_BUDGET
    actor_id: str = ""
    actor_kind: str = ""

    def __post_init__(self) -> None:
        if self.tool_budget < 0:
            raise ValueError("tool_budget must not be negative")

    @property
    def is_attributed(self) -> bool:
        """Return whether this run names the principal that caused it."""
        return bool(self.actor_id)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this context."""
        return {
            "team_id": self.team_id,
            "integrations": list(self.integrations),
            "sandbox_profiles": list(self.sandbox_profiles),
            "destinations": list(self.destinations),
            "tool_budget": self.tool_budget,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> TeamContext:
        """Return the context a stored record describes."""
        return cls(
            team_id=str(record.get("team_id", "")),
            integrations=tuple(str(item) for item in record.get("integrations") or ()),
            sandbox_profiles=tuple(str(item) for item in record.get("sandbox_profiles") or ()),
            destinations=tuple(str(item) for item in record.get("destinations") or ()),
            tool_budget=int(record.get("tool_budget", DEFAULT_TOOL_BUDGET)),
            actor_id=str(record.get("actor_id", "")),
            actor_kind=str(record.get("actor_kind", "")),
        )


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One thing said in the conversation this investigation belongs to."""

    author: str
    text: str
    at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this message."""
        return {
            "author": self.author,
            "text": self.text,
            "at": self.at.isoformat() if self.at else "",
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ChatMessage:
        """Return the message a stored record describes."""
        stamp = str(record.get("at", ""))
        return cls(
            author=str(record["author"]),
            text=str(record.get("text", "")),
            at=datetime.fromisoformat(stamp) if stamp else None,
        )


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """An action waiting on a human, recorded so a surface can show it.

    The pipeline records requests and never resolves them. Deciding is feature
    017's job, and putting the decision here would mean two places could grant
    the same approval.
    """

    request_id: str
    capability: str
    reason: str = ""
    arguments_digest: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this request."""
        return {
            "request_id": self.request_id,
            "capability": self.capability,
            "reason": self.reason,
            "arguments_digest": self.arguments_digest,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ApprovalRequest:
        """Return the request a stored record describes."""
        return cls(
            request_id=str(record["request_id"]),
            capability=str(record["capability"]),
            reason=str(record.get("reason", "")),
            arguments_digest=str(record.get("arguments_digest", "")),
        )


def unique_names(values: Sequence[str]) -> tuple[str, ...]:
    """Return ``values`` deduplicated with blanks dropped, order preserved."""
    seen: dict[str, None] = {}
    for value in values:
        trimmed = value.strip()
        if trimmed:
            seen.setdefault(trimmed, None)
    return tuple(seen)


__all__ = [
    "STAGE_ORDER",
    "ApprovalRequest",
    "ChatMessage",
    "IntakeClassification",
    "InvestigationOutcome",
    "OutcomeKind",
    "SliceName",
    "StageName",
    "TeamContext",
    "unique_names",
]
