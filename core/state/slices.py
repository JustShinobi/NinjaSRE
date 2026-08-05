"""Six frozen slices, one per concern, replaced wholesale rather than mutated.

Frozen is what makes stage purity checkable. A stage returns updates and the
merge function replaces whole slices, so "did this stage write outside what it
declared" is a comparison between two immutable values rather than a question
about who held a reference to what. Mutable slices would make the same question
answerable only by instrumenting every setter.

The partition is by *who writes*, not by what is convenient to read together.
Evidence is its own slice because the gathering stage is the only thing that
appends to it and the diagnosis stage is the only thing that must not.
Accounting is its own slice because every stage contributes cost and none of
them should be able to edit a conclusion while doing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.alerts.window import IncidentWindow
from core.domain.correlation.fingerprint import IncidentLink
from core.domain.correlation.planning import EMPTY_PLAN, EvidencePlan
from core.domain.diagnosis.result import DeliveryOutcome, Diagnosis
from core.llm.usage import TokenCounts
from core.state.catalogue import NO_CAPABILITIES, ResolvedCapabilities
from core.state.evidence import EvidenceEntry
from core.state.types import (
    ApprovalRequest,
    ChatMessage,
    IntakeClassification,
    InvestigationOutcome,
)


@dataclass(frozen=True, slots=True)
class ChatSlice:
    """The conversation this investigation belongs to.

    Held apart from the investigation because a run started from a webhook has
    no conversation at all, and an empty tuple is a more honest answer than an
    investigation slice with three chat-shaped fields nobody filled in.
    """

    messages: tuple[ChatMessage, ...] = ()
    channel: str = ""
    thread_id: str = ""

    def with_message(self, message: ChatMessage) -> ChatSlice:
        """Return this slice with ``message`` appended."""
        return replace(self, messages=(*self.messages, message))

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {
            "messages": [message.to_record() for message in self.messages],
            "channel": self.channel,
            "thread_id": self.thread_id,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ChatSlice:
        """Return the slice a stored record describes."""
        return cls(
            messages=tuple(ChatMessage.from_record(item) for item in record.get("messages") or ()),
            channel=str(record.get("channel", "")),
            thread_id=str(record.get("thread_id", "")),
        )


@dataclass(frozen=True, slots=True)
class InvestigationSlice:
    """What the run established, from the catalogue through to the delivery.

    Every stage writes exactly one or two named fields here, and the ownership
    table says which. That is the whole reason this is one slice with many
    fields rather than six slices with one each: the fields are read together
    constantly and written apart strictly, and only the second needs enforcing.
    """

    catalogue: ResolvedCapabilities = NO_CAPABILITIES
    alert: NormalisedAlert | None = None
    window: IncidentWindow | None = None
    classification: IntakeClassification | None = None
    link: IncidentLink | None = None
    plan: EvidencePlan = EMPTY_PLAN
    conclusion: str = ""
    diagnosis: Diagnosis | None = None
    delivery: DeliveryOutcome | None = None
    outcome: InvestigationOutcome | None = None

    @property
    def halted(self) -> bool:
        """Return whether an outcome has been reached that stops the remaining stages."""
        return self.outcome is not None and self.outcome.halts

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {
            "catalogue": self.catalogue.to_record(),
            "alert": self.alert.to_record() if self.alert else None,
            "window": self.window.to_record() if self.window else None,
            "classification": self.classification.to_record() if self.classification else None,
            "link": self.link.to_record() if self.link else None,
            "plan": self.plan.to_record(),
            "conclusion": self.conclusion,
            "diagnosis": self.diagnosis.to_record() if self.diagnosis else None,
            "delivery": self.delivery.to_record() if self.delivery else None,
            "outcome": self.outcome.to_record() if self.outcome else None,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> InvestigationSlice:
        """Return the slice a stored record describes."""
        return cls(
            catalogue=ResolvedCapabilities.from_record(record.get("catalogue") or {}),
            alert=_optional(record.get("alert"), NormalisedAlert.from_record),
            window=_optional(record.get("window"), IncidentWindow.from_record),
            classification=_optional(
                record.get("classification"), IntakeClassification.from_record
            ),
            link=_optional(record.get("link"), IncidentLink.from_record),
            plan=EvidencePlan.from_record(record.get("plan") or {}),
            conclusion=str(record.get("conclusion", "")),
            diagnosis=_optional(record.get("diagnosis"), Diagnosis.from_record),
            delivery=_optional(record.get("delivery"), DeliveryOutcome.from_record),
            outcome=_optional(record.get("outcome"), InvestigationOutcome.from_record),
        )


@dataclass(frozen=True, slots=True)
class EvidenceSlice:
    """Every observation the run holds, in the order it made them."""

    entries: tuple[EvidenceEntry, ...] = ()

    def __len__(self) -> int:
        """Return how many observations the run holds."""
        return len(self.entries)

    @property
    def ids(self) -> frozenset[str]:
        """Return the identifiers a claim is allowed to cite."""
        return frozenset(entry.id for entry in self.entries)

    def find(self, evidence_id: str) -> EvidenceEntry | None:
        """Return the entry with ``evidence_id``, or ``None``."""
        return next((entry for entry in self.entries if entry.id == evidence_id), None)

    def extended(self, entries: tuple[EvidenceEntry, ...]) -> EvidenceSlice:
        """Return this slice with ``entries`` appended."""
        return replace(self, entries=(*self.entries, *entries))

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {"entries": [entry.to_record() for entry in self.entries]}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> EvidenceSlice:
        """Return the slice a stored record describes."""
        return cls(
            entries=tuple(EvidenceEntry.from_record(item) for item in record.get("entries") or ())
        )


@dataclass(frozen=True, slots=True)
class AccountingSlice:
    """What the run cost, and how far the loop got.

    ``status`` is the runtime's own word for how the run ended. It is carried
    rather than recomputed because a partial run that produced eleven
    observations is a different thing from a completed one that produced
    eleven, and only the runtime knows which happened.
    """

    tokens: TokenCounts = TokenCounts()
    llm_calls: int = 0
    capability_executions: int = 0
    iterations: int = 0
    runtime: str = ""
    status: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {
            "tokens": {
                "input_tokens": self.tokens.input_tokens,
                "output_tokens": self.tokens.output_tokens,
                "cached_input_tokens": self.tokens.cached_input_tokens,
                "cache_write_tokens": self.tokens.cache_write_tokens,
                "reasoning_tokens": self.tokens.reasoning_tokens,
                "estimated": self.tokens.estimated,
            },
            "llm_calls": self.llm_calls,
            "capability_executions": self.capability_executions,
            "iterations": self.iterations,
            "runtime": self.runtime,
            "status": self.status,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> AccountingSlice:
        """Return the slice a stored record describes."""
        counts = record.get("tokens") or {}
        return cls(
            tokens=TokenCounts(
                input_tokens=int(counts.get("input_tokens", 0)),
                output_tokens=int(counts.get("output_tokens", 0)),
                cached_input_tokens=int(counts.get("cached_input_tokens", 0)),
                cache_write_tokens=int(counts.get("cache_write_tokens", 0)),
                reasoning_tokens=int(counts.get("reasoning_tokens", 0)),
                estimated=bool(counts.get("estimated", False)),
            ),
            llm_calls=int(record.get("llm_calls", 0)),
            capability_executions=int(record.get("capability_executions", 0)),
            iterations=int(record.get("iterations", 0)),
            runtime=str(record.get("runtime", "")),
            status=str(record.get("status", "")),
        )


@dataclass(frozen=True, slots=True)
class ApprovalSlice:
    """Actions this run asked a human to accept.

    Requests only. The pipeline never records a decision, because deciding is a
    separate feature's job and two places able to grant the same approval is
    one place too many.
    """

    requests: tuple[ApprovalRequest, ...] = ()

    @property
    def pending(self) -> bool:
        """Return whether anything is waiting on a human."""
        return bool(self.requests)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {"requests": [request.to_record() for request in self.requests]}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ApprovalSlice:
        """Return the slice a stored record describes."""
        return cls(
            requests=tuple(
                ApprovalRequest.from_record(item) for item in record.get("requests") or ()
            )
        )


@dataclass(frozen=True, slots=True)
class MemorySlice:
    """What past investigations contributed, and what this one will leave behind.

    Empty until the memory layer lands. It is declared now because the fields
    episode extraction consumes have to exist before the extractor does, and
    retrofitting a slice means retrofitting the ownership table and every
    purity test that reads it.
    """

    recalled_episodes: tuple[str, ...] = ()
    recalled_strategies: tuple[str, ...] = ()
    episode_id: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this slice."""
        return {
            "recalled_episodes": list(self.recalled_episodes),
            "recalled_strategies": list(self.recalled_strategies),
            "episode_id": self.episode_id,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> MemorySlice:
        """Return the slice a stored record describes."""
        return cls(
            recalled_episodes=tuple(str(item) for item in record.get("recalled_episodes") or ()),
            recalled_strategies=tuple(
                str(item) for item in record.get("recalled_strategies") or ()
            ),
            episode_id=str(record.get("episode_id", "")),
        )


def _optional[T](record: object, build: Callable[[dict[str, Any]], T]) -> T | None:
    """Return ``build(record)`` when the record is present, or ``None``.

    An absent optional field and one stored as ``null`` are the same absence,
    and so is an empty object — nothing round-trips to a slice field holding a
    value with no fields set.
    """
    if not isinstance(record, dict) or not record:
        return None
    return build(record)


__all__ = [
    "AccountingSlice",
    "ApprovalSlice",
    "ChatSlice",
    "EvidenceSlice",
    "InvestigationSlice",
    "MemorySlice",
]
