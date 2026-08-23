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

    ``INTERRUPTED`` is the one word the runtime has no use for, because a
    process that vanished did not get to record anything. It is written *for* a
    run by whoever noticed it stopped — a reaper finding an expired lease, a
    replica finding a run still marked running at boot — and it says something
    ``FAILED`` does not: nobody knows how far this got. Recording it as a
    failure would put a conclusion in the history that nothing established.
    """

    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


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
    #: One sentence naming the run, apart from the document ``summary``
    #: holds. Empty for a run that has not concluded yet, or one recorded
    #: before this field existed — a reader synthesises a headline for
    #: either case rather than treating the empty string as the run's name.
    headline: str = ""
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
class TraceEventRecord:
    """One thing that happened during a run, at its position in the run's log.

    The four records above are *state*: what the run is, what it thought, what
    it called, what it saw. This one is the *order those arrived in*, and it is
    a separate record because a client that disconnects and comes back has to
    ask a question the other four cannot answer — "what happened after position
    N" — without replaying the whole investigation to find out.

    ``sequence`` is assigned by the store, not by the caller. It is the cursor a
    reconnecting client presents, so two writers must not be able to choose the
    same one, and a caller that picked its own would be choosing on behalf of
    every other writer to the same run.
    """

    event_id: str
    run_id: str
    kind: str
    occurred_at: datetime | None = None
    turn_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    sequence: int = 0


@dataclass(frozen=True, slots=True)
class RunTrace:
    """A run and everything under it, assembled for replay."""

    run: AgentRun
    turns: tuple[TurnRecord, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    events: tuple[TraceEventRecord, ...] = ()


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
        headline: str | None = None,
    ) -> AgentRun:
        """Close ``run_id`` with a terminal status and return the stored run.

        ``headline`` is left unchanged when ``None`` — the same convention
        ``summary`` already uses — so a caller that only has one of the two
        to report does not overwrite the other with emptiness.

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

    async def record_event(self, event: TraceEventRecord) -> TraceEventRecord:
        """Append ``event`` to its run's log and return it carrying its cursor.

        The returned ``sequence`` is the store's, whatever the caller passed.
        Raises ``RecordNotFound`` when the run does not exist.
        """

    async def events_for_run(
        self,
        run_id: str,
        *,
        after: int | None = None,
        limit: int = 50,
    ) -> tuple[TraceEventRecord, ...]:
        """Return the run's events in log order, strictly after ``after``.

        ``after`` is a cursor a client held when it lost its connection, so the
        bound is exclusive: an event it already saw must not arrive twice.
        ``limit`` is capped by ``MAX_QUERY_PAGE_SIZE``; above it,
        ``BoundExceeded``.
        """

    async def strip_trace(self, run_id: str) -> int:
        """Delete the run's turns, calls, evidence, and events; keep the run.

        Returns how many records went. The run row itself — its identity,
        status, timings, and outcome summary — survives, which is what lets
        retention reclaim the bulk of a trace without erasing the fact that the
        investigation happened or what it concluded. Raises ``RecordNotFound``
        when the run does not exist: stripping a trace that is not there is
        almost always a caller working from a stale list.
        """

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
    "TraceEventRecord",
    "TurnRecord",
]
