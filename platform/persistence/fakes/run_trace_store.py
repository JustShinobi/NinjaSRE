"""In-memory runs, turns, tool calls, and evidence."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from config.constants.runs import STAGE_EVENT_NAME
from platform.persistence.errors import DuplicateRecord, RecordNotFound
from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    RunStatus,
    RunTrace,
    ToolCallRecord,
    TraceEventRecord,
    TurnRecord,
)
from platform.runs.events import TraceEventKind


@dataclass(slots=True)
class FakeRunTraceStore:
    """Traces for one organisation."""

    org_id: str
    state: TenantState

    async def start_run(self, run: AgentRun) -> AgentRun:
        """Record a run beginning and return it."""
        if run.run_id in self.state.runs:
            raise DuplicateRecord(kind="agent run", identifier=run.run_id)
        check_payload(run.metadata, kind="agent run metadata")
        self.state.runs[run.run_id] = run
        return run

    async def complete_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        finished_at: datetime,
        summary: str | None = None,
        headline: str | None = None,
    ) -> AgentRun:
        """Close ``run_id`` with a terminal status and return the stored run."""
        run = self._require_run(run_id)
        stored = replace(
            run,
            status=status,
            finished_at=finished_at,
            summary=summary if summary is not None else run.summary,
            headline=headline if headline is not None else run.headline,
        )
        self.state.runs[run_id] = stored
        return stored

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Return the run with ``run_id``, or ``None``."""
        return self.state.runs.get(run_id)

    async def last_completed_stages(self, run_ids: Sequence[str]) -> Mapping[str, str]:
        """Return each run's last completed stage, from the events already held."""
        wanted = set(run_ids)
        latest: dict[str, tuple[int, str]] = {}
        for event in self.state.trace_events.values():
            if event.run_id not in wanted or event.kind != TraceEventKind.STAGE_COMPLETED.value:
                continue
            stage = str(event.payload.get(STAGE_EVENT_NAME, ""))
            if not stage:
                continue
            current = latest.get(event.run_id)
            if current is None or event.sequence > current[0]:
                latest[event.run_id] = (event.sequence, stage)
        return {run_id: stage for run_id, (_, stage) in latest.items()}

    async def list_runs(
        self,
        *,
        status: RunStatus | Collection[RunStatus] | None = None,
        alert_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        run_ids: Collection[str] | None = None,
        limit: int = 50,
    ) -> tuple[AgentRun, ...]:
        """Return matching runs, most recently started first."""
        check_limit(limit)
        wanted = _statuses(status)
        named = None if run_ids is None else frozenset(run_ids)
        matches = [
            run
            for run in self.state.runs.values()
            if (wanted is None or run.status in wanted)
            and (named is None or run.run_id in named)
            and (alert_id is None or run.alert_id == alert_id)
            and _within(run.started_at, since, until)
        ]
        matches.sort(key=_run_order, reverse=True)
        return tuple(matches[:limit])

    async def record_turn(self, turn: TurnRecord) -> TurnRecord:
        """Store one turn of ``turn.run_id`` and return it."""
        self._require_run(turn.run_id)
        check_payload(turn.payload, kind="turn")
        self.state.turns[turn.turn_id] = turn
        return turn

    async def record_tool_call(self, call: ToolCallRecord) -> ToolCallRecord:
        """Store one tool call and return it."""
        self._require_run(call.run_id)
        check_payload(call.arguments, kind="tool call arguments")
        self.state.tool_calls[call.call_id] = call
        return call

    async def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        """Store one observation and return it."""
        self._require_run(evidence.run_id)
        check_payload(evidence.body, kind="evidence")
        self.state.evidence[evidence.evidence_id] = evidence
        return evidence

    async def mark_cited(self, evidence_id: str) -> bool:
        """Mark evidence as cited by a conclusion, and return whether it existed."""
        evidence = self.state.evidence.get(evidence_id)
        if evidence is None:
            return False
        self.state.evidence[evidence_id] = replace(evidence, cited=True)
        return True

    async def turns_for_run(self, run_id: str) -> tuple[TurnRecord, ...]:
        """Return the run's turns in index order."""
        turns = [t for t in self.state.turns.values() if t.run_id == run_id]
        return tuple(sorted(turns, key=lambda t: (t.index, t.turn_id)))

    async def tool_calls_for_run(self, run_id: str) -> tuple[ToolCallRecord, ...]:
        """Return the run's tool calls in the order they were recorded."""
        return tuple(c for c in self.state.tool_calls.values() if c.run_id == run_id)

    async def named_tool_calls_for_runs(
        self, run_ids: Sequence[str], tool_name: str
    ) -> tuple[ToolCallRecord, ...]:
        """Return every call of ``tool_name`` across ``run_ids``, recording order."""
        wanted = set(run_ids)
        return tuple(
            c
            for c in self.state.tool_calls.values()
            if c.run_id in wanted and c.tool_name == tool_name
        )

    async def evidence_for_run(self, run_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the run's evidence in the order it was observed."""
        return tuple(e for e in self.state.evidence.values() if e.run_id == run_id)

    async def record_event(self, event: TraceEventRecord) -> TraceEventRecord:
        """Append ``event`` to its run's log and return it carrying its cursor."""
        self._require_run(event.run_id)
        check_payload(event.payload, kind="trace event")
        stored = replace(event, sequence=self._next_sequence(event.run_id))
        self.state.trace_events[stored.event_id] = stored
        return stored

    async def events_for_run(
        self,
        run_id: str,
        *,
        after: int | None = None,
        limit: int = 50,
    ) -> tuple[TraceEventRecord, ...]:
        """Return the run's events in log order, strictly after ``after``."""
        check_limit(limit)
        matches = [
            event
            for event in self.state.trace_events.values()
            if event.run_id == run_id and (after is None or event.sequence > after)
        ]
        matches.sort(key=lambda event: event.sequence)
        return tuple(matches[:limit])

    async def strip_trace(self, run_id: str) -> int:
        """Delete the run's turns, calls, evidence, and events; keep the run."""
        self._require_run(run_id)
        removed = 0
        for held in (
            self.state.turns,
            self.state.tool_calls,
            self.state.evidence,
            self.state.trace_events,
        ):
            expired = [key for key, record in held.items() if record.run_id == run_id]
            for key in expired:
                del held[key]
            removed += len(expired)
        return removed

    async def replay(self, run_id: str) -> RunTrace:
        """Return the whole trace of ``run_id``, assembled."""
        run = self._require_run(run_id)
        return RunTrace(
            run=run,
            turns=await self.turns_for_run(run_id),
            tool_calls=await self.tool_calls_for_run(run_id),
            evidence=await self.evidence_for_run(run_id),
            events=await self.events_for_run(run_id, limit=MAX_QUERY_PAGE_SIZE),
        )

    def _next_sequence(self, run_id: str) -> int:
        """Return the next position in one run's log.

        Per run rather than global: the cursor a client holds is a position
        within the run it is watching, and a deployment-wide counter would leak
        how busy the rest of the deployment was between two of its events.
        """
        held = [
            event.sequence for event in self.state.trace_events.values() if event.run_id == run_id
        ]
        return max(held, default=-1) + 1

    def _require_run(self, run_id: str) -> AgentRun:
        run = self.state.runs.get(run_id)
        if run is None:
            raise RecordNotFound(kind="agent run", identifier=run_id)
        return run


#: Sorts before any real timestamp, so a run that has not started yet orders
#: last under a descending sort instead of making the key incomparable.
_UNSTARTED = datetime.min.replace(tzinfo=UTC)


def _run_order(run: AgentRun) -> tuple[datetime, str]:
    """Order runs by start time, with the id breaking ties deterministically."""
    return (run.started_at or _UNSTARTED, run.run_id)


def _within(
    moment: datetime | None,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    """Return whether ``moment`` falls in a half-open window.

    A run with no start time matches only an unfiltered query: it has not
    happened yet, so claiming it happened in some window would be an invention.
    """
    if moment is None:
        return since is None and until is None
    if since is not None and moment < since:
        return False
    return not (until is not None and moment >= until)


__all__ = ["FakeRunTraceStore"]


def _statuses(status: RunStatus | Collection[RunStatus] | None) -> frozenset[RunStatus] | None:
    """Return the statuses a listing asked for, or ``None`` for all of them."""
    if status is None:
        return None
    if isinstance(status, RunStatus):
        return frozenset({status})
    return frozenset(status)
