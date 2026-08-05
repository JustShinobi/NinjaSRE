"""In-memory runs, turns, tool calls, and evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.errors import DuplicateRecord, RecordNotFound
from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    RunStatus,
    RunTrace,
    ToolCallRecord,
    TurnRecord,
)


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
    ) -> AgentRun:
        """Close ``run_id`` with a terminal status and return the stored run."""
        run = self._require_run(run_id)
        stored = replace(
            run,
            status=status,
            finished_at=finished_at,
            summary=summary if summary is not None else run.summary,
        )
        self.state.runs[run_id] = stored
        return stored

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Return the run with ``run_id``, or ``None``."""
        return self.state.runs.get(run_id)

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        alert_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> tuple[AgentRun, ...]:
        """Return matching runs, most recently started first."""
        check_limit(limit)
        matches = [
            run
            for run in self.state.runs.values()
            if (status is None or run.status is status)
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

    async def evidence_for_run(self, run_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the run's evidence in the order it was observed."""
        return tuple(e for e in self.state.evidence.values() if e.run_id == run_id)

    async def replay(self, run_id: str) -> RunTrace:
        """Return the whole trace of ``run_id``, assembled."""
        run = self._require_run(run_id)
        return RunTrace(
            run=run,
            turns=await self.turns_for_run(run_id),
            tool_calls=await self.tool_calls_for_run(run_id),
            evidence=await self.evidence_for_run(run_id),
        )

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
