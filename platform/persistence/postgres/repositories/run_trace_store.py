"""Runs, turns, tool calls, evidence, and the event log over PostgreSQL."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select

from config.constants.persistence import MAX_JSONB_PAYLOAD_BYTES, MAX_QUERY_PAGE_SIZE
from platform.persistence.errors import DuplicateRecord, PayloadTooLarge, RecordNotFound
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    RunStatus,
    RunTrace,
    ToolCallRecord,
    ToolCallStatus,
    TraceEventRecord,
    TurnRecord,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    check_limit,
    rows_affected,
    translating,
)


def check_payload(payload: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    """Return ``payload`` as a dict, or raise if its JSON form is too large.

    Checked here rather than left to PostgreSQL. A JSONB value larger than a
    page is TOASTed silently and works — until a restore, a replication lag
    spike, or a console query that fetches a thousand of them.
    """
    body = dict(payload)
    size = len(json.dumps(body).encode("utf-8"))
    if size > MAX_JSONB_PAYLOAD_BYTES:
        raise PayloadTooLarge(kind=kind, size_bytes=size, limit_bytes=MAX_JSONB_PAYLOAD_BYTES)
    return body


def _to_run(row: models.AgentRun) -> AgentRun:
    return AgentRun(
        run_id=row.run_id,
        trigger=row.trigger,
        status=RunStatus(row.status),
        started_at=as_utc(row.started_at),
        finished_at=as_utc(row.finished_at),
        alert_id=row.alert_id,
        runtime=row.runtime,
        model_id=row.model_id,
        summary=row.summary,
        metadata=dict(row.run_metadata),
    )


def _to_turn(row: models.RunTurn) -> TurnRecord:
    return TurnRecord(
        turn_id=row.turn_id,
        run_id=row.run_id,
        index=row.index,
        started_at=as_utc(row.started_at),
        finished_at=as_utc(row.finished_at),
        payload=dict(row.payload),
        usage=dict(row.usage),
    )


def _to_call(row: models.ToolCall) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=row.call_id,
        run_id=row.run_id,
        turn_id=row.turn_id,
        tool_name=row.tool_name,
        status=ToolCallStatus(row.status),
        arguments=dict(row.arguments),
        started_at=as_utc(row.started_at),
        finished_at=as_utc(row.finished_at),
        error=row.error,
        evidence_ids=as_tuple(row.evidence_ids),
    )


def _to_event(row: models.TraceEvent) -> TraceEventRecord:
    return TraceEventRecord(
        event_id=row.event_id,
        run_id=row.run_id,
        kind=row.kind,
        occurred_at=as_utc(row.occurred_at),
        turn_id=row.turn_id,
        payload=dict(row.payload),
        sequence=row.sequence,
    )


def _to_evidence(row: models.Evidence) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row.evidence_id,
        run_id=row.run_id,
        source=row.source,
        evidence_type=row.evidence_type,
        observed_at=as_utc(row.observed_at),
        body=dict(row.body),
        cited=row.cited,
    )


@dataclass(slots=True)
class PostgresRunTraceStore(TenantBound):
    """Traces for one organisation."""

    async def start_run(self, run: AgentRun) -> AgentRun:
        """Record a run beginning and return it."""
        if await self.session.get(models.AgentRun, (self.org_id, run.run_id)) is not None:
            raise DuplicateRecord(kind="agent run", identifier=run.run_id)

        row = models.AgentRun(
            org_id=self.org_id,
            run_id=run.run_id,
            trigger=run.trigger,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            alert_id=run.alert_id,
            runtime=run.runtime,
            model_id=run.model_id,
            summary=run.summary,
            run_metadata=check_payload(run.metadata, kind="agent run metadata"),
        )
        self.session.add(row)
        with translating(kind="agent run", identifier=run.run_id):
            await self.session.flush()
        return _to_run(row)

    async def complete_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        finished_at: datetime,
        summary: str | None = None,
    ) -> AgentRun:
        """Close ``run_id`` with a terminal status and return the stored run."""
        row = await self._require_run(run_id)
        row.status = status.value
        row.finished_at = finished_at
        if summary is not None:
            row.summary = summary
        await self.session.flush()
        return _to_run(row)

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Return the run with ``run_id``, or ``None``."""
        row = await self.session.get(models.AgentRun, (self.org_id, run_id))
        return _to_run(row) if row is not None else None

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
        statement = (
            select(models.AgentRun)
            .where(models.AgentRun.org_id == self.org_id)
            .order_by(models.AgentRun.started_at.desc(), models.AgentRun.run_id.desc())
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(models.AgentRun.status == status.value)
        if alert_id is not None:
            statement = statement.where(models.AgentRun.alert_id == alert_id)
        if since is not None:
            statement = statement.where(models.AgentRun.started_at >= since)
        if until is not None:
            statement = statement.where(models.AgentRun.started_at < until)
        if since is not None or until is not None:
            # A run with no start time has not happened yet, so claiming it
            # happened in some window would be an invention.
            statement = statement.where(models.AgentRun.started_at.is_not(None))

        rows = await self.session.scalars(statement)
        return tuple(_to_run(row) for row in rows)

    async def record_turn(self, turn: TurnRecord) -> TurnRecord:
        """Store one turn of ``turn.run_id`` and return it."""
        await self._require_run(turn.run_id)
        row = models.RunTurn(
            org_id=self.org_id,
            turn_id=turn.turn_id,
            run_id=turn.run_id,
            index=turn.index,
            started_at=turn.started_at,
            finished_at=turn.finished_at,
            payload=check_payload(turn.payload, kind="turn"),
            usage=check_payload(turn.usage, kind="turn usage"),
        )
        await self.session.merge(row)
        with translating(kind="turn", identifier=turn.turn_id, referenced="agent run"):
            await self.session.flush()
        return turn

    async def record_tool_call(self, call: ToolCallRecord) -> ToolCallRecord:
        """Store one tool call and return it."""
        await self._require_run(call.run_id)
        row = models.ToolCall(
            org_id=self.org_id,
            call_id=call.call_id,
            run_id=call.run_id,
            turn_id=call.turn_id,
            tool_name=call.tool_name,
            status=call.status.value,
            arguments=check_payload(call.arguments, kind="tool call arguments"),
            started_at=call.started_at,
            finished_at=call.finished_at,
            error=call.error,
            evidence_ids=as_list(call.evidence_ids),
            recorded_seq=await self._next_sequence(models.ToolCall, call.run_id),
        )
        await self.session.merge(row)
        with translating(kind="tool call", identifier=call.call_id, referenced="agent run"):
            await self.session.flush()
        return call

    async def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        """Store one observation and return it."""
        await self._require_run(evidence.run_id)
        row = models.Evidence(
            org_id=self.org_id,
            evidence_id=evidence.evidence_id,
            run_id=evidence.run_id,
            source=evidence.source,
            evidence_type=evidence.evidence_type,
            observed_at=evidence.observed_at,
            body=check_payload(evidence.body, kind="evidence"),
            cited=evidence.cited,
            recorded_seq=await self._next_sequence(models.Evidence, evidence.run_id),
        )
        await self.session.merge(row)
        with translating(kind="evidence", identifier=evidence.evidence_id, referenced="agent run"):
            await self.session.flush()
        return evidence

    async def mark_cited(self, evidence_id: str) -> bool:
        """Mark evidence as cited by a conclusion, and return whether it existed."""
        row = await self.session.get(models.Evidence, (self.org_id, evidence_id))
        if row is None:
            return False
        row.cited = True
        await self.session.flush()
        return True

    async def turns_for_run(self, run_id: str) -> tuple[TurnRecord, ...]:
        """Return the run's turns in index order."""
        rows = await self.session.scalars(
            select(models.RunTurn)
            .where(models.RunTurn.org_id == self.org_id, models.RunTurn.run_id == run_id)
            .order_by(models.RunTurn.index, models.RunTurn.turn_id)
        )
        return tuple(_to_turn(row) for row in rows)

    async def tool_calls_for_run(self, run_id: str) -> tuple[ToolCallRecord, ...]:
        """Return the run's tool calls in the order they were recorded."""
        rows = await self.session.scalars(
            select(models.ToolCall)
            .where(models.ToolCall.org_id == self.org_id, models.ToolCall.run_id == run_id)
            .order_by(models.ToolCall.recorded_seq, models.ToolCall.call_id)
        )
        return tuple(_to_call(row) for row in rows)

    async def evidence_for_run(self, run_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the run's evidence in the order it was observed."""
        rows = await self.session.scalars(
            select(models.Evidence)
            .where(models.Evidence.org_id == self.org_id, models.Evidence.run_id == run_id)
            .order_by(models.Evidence.recorded_seq, models.Evidence.evidence_id)
        )
        return tuple(_to_evidence(row) for row in rows)

    async def record_event(self, event: TraceEventRecord) -> TraceEventRecord:
        """Append ``event`` to its run's log and return it carrying its cursor."""
        await self._require_run(event.run_id)
        sequence = await self._next_event_sequence(event.run_id)
        row = models.TraceEvent(
            org_id=self.org_id,
            event_id=event.event_id,
            run_id=event.run_id,
            turn_id=event.turn_id,
            kind=event.kind,
            occurred_at=event.occurred_at,
            payload=check_payload(event.payload, kind="trace event"),
            sequence=sequence,
        )
        await self.session.merge(row)
        with translating(kind="trace event", identifier=event.event_id, referenced="agent run"):
            await self.session.flush()
        return _to_event(row)

    async def events_for_run(
        self,
        run_id: str,
        *,
        after: int | None = None,
        limit: int = 50,
    ) -> tuple[TraceEventRecord, ...]:
        """Return the run's events in log order, strictly after ``after``."""
        check_limit(limit)
        statement = (
            select(models.TraceEvent)
            .where(models.TraceEvent.org_id == self.org_id, models.TraceEvent.run_id == run_id)
            .order_by(models.TraceEvent.sequence)
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(models.TraceEvent.sequence > after)

        rows = await self.session.scalars(statement)
        return tuple(_to_event(row) for row in rows)

    async def strip_trace(self, run_id: str) -> int:
        """Delete the run's turns, calls, evidence, and events; keep the run."""
        await self._require_run(run_id)
        removed = 0
        for model in (models.RunTurn, models.ToolCall, models.Evidence, models.TraceEvent):
            result = await self.session.execute(
                delete(model).where(model.org_id == self.org_id, model.run_id == run_id)
            )
            removed += rows_affected(result)
        await self.session.flush()
        # The identity map still holds the rows the DELETE removed, and a later
        # read in the same unit of work would be served from it.
        self.session.expunge_all()
        return removed

    async def replay(self, run_id: str) -> RunTrace:
        """Return the whole trace of ``run_id``, assembled."""
        run = await self._require_run(run_id)
        return RunTrace(
            run=_to_run(run),
            turns=await self.turns_for_run(run_id),
            tool_calls=await self.tool_calls_for_run(run_id),
            evidence=await self.evidence_for_run(run_id),
            events=await self.events_for_run(run_id, limit=MAX_QUERY_PAGE_SIZE),
        )

    async def _require_run(self, run_id: str) -> models.AgentRun:
        row = await self.session.get(models.AgentRun, (self.org_id, run_id))
        if row is None:
            raise RecordNotFound(kind="agent run", identifier=run_id)
        return row

    async def _next_sequence(
        self,
        model: type[models.ToolCall] | type[models.Evidence],
        run_id: str,
    ) -> int:
        """Return the next arrival position within one run.

        Tool calls and evidence are ordered by *arrival*, not by timestamp: two
        calls in one concurrent batch routinely share a microsecond, and a
        replay whose order changes between reads is not a replay. The counter is
        per run and assigned inside the run's own transaction, so there is no
        cross-run contention to serialise on.
        """
        current = await self.session.scalar(
            select(func.coalesce(func.max(model.recorded_seq), -1)).where(
                model.org_id == self.org_id, model.run_id == run_id
            )
        )
        return _after(current)

    async def _next_event_sequence(self, run_id: str) -> int:
        """Return the next position in one run's event log.

        Per run rather than global. The cursor a client holds is a position
        within the run it is watching, and a deployment-wide counter would both
        serialise every writer on one row and leak how busy the rest of the
        deployment was between two of that client's events.
        """
        current = await self.session.scalar(
            select(func.coalesce(func.max(models.TraceEvent.sequence), -1)).where(
                models.TraceEvent.org_id == self.org_id,
                models.TraceEvent.run_id == run_id,
            )
        )
        return _after(current)


def _after(highest: int | None) -> int:
    """Return the position following ``highest``, or the first one.

    Written out rather than ``int(highest or -1) + 1``, which is the same
    expression with one wrong answer in it: position 0 is falsy, so the second
    record in every run would be handed 0 as well and the ordering would
    silently collapse onto the tie-breaker.
    """
    return (-1 if highest is None else int(highest)) + 1


__all__ = ["PostgresRunTraceStore", "check_payload"]
