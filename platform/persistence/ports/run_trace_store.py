"""The durable form of an investigation, complete enough to replay offline.

Article I says a conclusion carries the observations that support it, and that a
tool result which never entered the trace did not happen. This port is where
that stops being an assertion. A run, its turns, the tool calls inside them, and
the evidence those produced are four kinds of record with one lifetime, and
``replay`` returns them assembled — which is the operation an ablation, a
regression triage, or an operator asking "why did it say that" actually needs.

Evidence is recorded separately from the turn that produced it, and deliberately
so. The transcript is what the model said; evidence is what the system observed,
and only the second is citable in a conclusion. Compaction rewrites transcripts.
It must never be able to rewrite evidence, and keeping them in different records
is what makes that structural rather than careful.

Bodies are JSONB and bounded by ``MAX_JSONB_PAYLOAD_BYTES``. A tool that returns
forty megabytes of logs stores a reference and a summary; storing the lot is how
a trace table outgrows the database it was meant to fit inside.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class RunStatus(StrEnum):
    """Where a run got to.

    Mirrors the runtime's own session status rather than inventing a second
    vocabulary: an operator reading a stored trace and an operator watching a
    live run should not have to translate between two sets of words.
    """

    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ToolCallStatus(StrEnum):
    """How one tool call ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class AgentRun:
    """One investigation, from the alert that triggered it to its conclusion."""

    run_id: str
    trigger: str
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    alert_id: str | None = None
    runtime: str | None = None
    model_id: str | None = None
    summary: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One iteration of the loop: what was sent, what came back, what it cost.

    ``index`` rather than a timestamp orders these. Two turns can share a
    millisecond; they cannot share a position.
    """

    turn_id: str
    run_id: str
    index: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """One capability invocation, with the arguments it was actually given."""

    call_id: str
    run_id: str
    turn_id: str
    tool_name: str
    status: ToolCallStatus = ToolCallStatus.SUCCEEDED
    arguments: Mapping[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One observation the system made, citable in a conclusion."""

    evidence_id: str
    run_id: str
    source: str
    evidence_type: str
    observed_at: datetime | None = None
    body: Mapping[str, Any] = field(default_factory=dict)
    cited: bool = False


@dataclass(frozen=True, slots=True)
class RunTrace:
    """A run and everything under it, assembled for replay."""

    run: AgentRun
    turns: tuple[TurnRecord, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()


@runtime_checkable
class RunTraceStore(Protocol):
    """Runs, turns, tool calls, and evidence, within one tenant."""

    async def start_run(self, run: AgentRun) -> AgentRun:
        """Record a run beginning and return it.

        Raises ``DuplicateRecord`` if ``run_id`` is already recorded.
        """

    async def complete_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        finished_at: datetime,
        summary: str | None = None,
    ) -> AgentRun:
        """Close ``run_id`` with a terminal status and return the stored run.

        Raises ``RecordNotFound`` when the run does not exist in this tenant.
        """

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Return the run with ``run_id``, or ``None``."""

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        alert_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> tuple[AgentRun, ...]:
        """Return matching runs, most recently started first.

        ``limit`` is capped by ``MAX_QUERY_PAGE_SIZE``; above it,
        ``BoundExceeded``.
        """

    async def record_turn(self, turn: TurnRecord) -> TurnRecord:
        """Store one turn of ``turn.run_id`` and return it.

        Raises ``RecordNotFound`` when the run does not exist, and
        ``PayloadTooLarge`` when the payload exceeds the JSONB bound.
        """

    async def record_tool_call(self, call: ToolCallRecord) -> ToolCallRecord:
        """Store one tool call and return it."""

    async def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        """Store one observation and return it."""

    async def mark_cited(self, evidence_id: str) -> bool:
        """Mark evidence as cited by a conclusion, and return whether it existed."""

    async def turns_for_run(self, run_id: str) -> tuple[TurnRecord, ...]:
        """Return the run's turns in index order."""

    async def tool_calls_for_run(self, run_id: str) -> tuple[ToolCallRecord, ...]:
        """Return the run's tool calls in the order they were recorded."""

    async def evidence_for_run(self, run_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the run's evidence in the order it was observed."""

    async def replay(self, run_id: str) -> RunTrace:
        """Return the whole trace of ``run_id``, assembled.

        Raises ``RecordNotFound`` rather than returning an empty trace. A run
        that produced nothing and a run that does not exist are different
        facts, and an ablation reading the second as the first would score a
        missing corpus as a bad one.
        """


__all__ = [
    "AgentRun",
    "EvidenceRecord",
    "RunStatus",
    "RunTrace",
    "RunTraceStore",
    "ToolCallRecord",
    "ToolCallStatus",
    "TurnRecord",
]
