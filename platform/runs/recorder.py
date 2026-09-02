"""Writing an investigation down while it happens.

Article I says a tool result that never entered the trace did not happen. This
module is where that becomes a thing the code does rather than a thing the
document says: one object owns every write to a run's trace, so "did this get
recorded" has one answer and one place to look for it.

Four properties are load-bearing, and each of them is a rule about *ordering*.

**Guardrails run before persistence, not after.** A secret that reached the
trace is a secret in a second store, one nobody audits and retention keeps for
ninety days. So the engine scans every string on the way in, and the resulting
redaction is what gets written — there is no path from a caller to the store
that skips it.

**Truncation happens before the store's own bound, and leaves a marker.** The
store raises above a megabyte, which is correct and much too late: the run has
already spent the time producing the payload. ``truncation`` brings it inside a
much smaller ceiling first, and records what that cost.

**The event goes to the log before it goes to the broker.** A subscriber that
received an event which is not yet in the log cannot be given it again after a
reconnect, and that is the exactly-once property gone. Log first, always.

**A sub-agent is a nested run, not a nested field.** Its turns and its calls are
its own records, linked to the parent, because the question worth asking about
delegation is what the sub-agent was given and what it came back with — and a
flattened trace cannot answer it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.runs import (
    RUN_METADATA_INTERRUPTION,
    RUN_METADATA_JOB,
    RUN_METADATA_PARENT,
    RUN_METADATA_PRINCIPAL,
    RUN_METADATA_SUBAGENT,
    RUN_METADATA_TEAM,
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
    STAGE_EVENT_DURATION_MS,
    STAGE_EVENT_FAILED,
    STAGE_EVENT_NAME,
    TRIGGER_SUBAGENT,
    TURN_PAYLOAD_CAPABILITIES,
    TURN_PAYLOAD_MODEL_RATIONALE,
    TURN_PAYLOAD_RATIONALE,
    TURN_USAGE_COMPLETION_TOKENS,
    TURN_USAGE_COST,
    TURN_USAGE_DURATION_MS,
    TURN_USAGE_MODEL,
    TURN_USAGE_PROMPT_TOKENS,
)
from core.agent.interaction.attention import (
    RUN_ATTENTION_KEY,
    RUN_ATTENTION_SINCE_KEY,
    Attention,
)
from platform.guardrails.engine import GuardrailEngine
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    RunStatus,
    RunTraceStore,
    ToolCallRecord,
    ToolCallStatus,
    TraceEventRecord,
    TurnRecord,
)
from platform.runs.events import RunEvent, TraceEventKind
from platform.runs.headline import resource_from_labels, synthesize_headline
from platform.runs.stream import RunEventPublisher
from platform.runs.truncation import truncate

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


def _identifier() -> str:
    """Return an identifier for a record the recorder is creating."""
    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class RecordedTurn:
    """One model call as the caller describes it, before it becomes a record.

    ``selection_rationale`` is here rather than derived because it is the half
    of a turn that cannot be reconstructed: the calls say what was chosen, and
    only this says why those capabilities were the ones on offer.
    """

    run_id: str
    index: int
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: ``None`` when the provider publishes no price for this model — never a
    #: stand-in zero. A turn that cost nothing to run does not exist; a turn
    #: nobody can price is the fact this field exists to keep distinguishable
    #: from one.
    cost: float | None = None
    duration_ms: int = 0
    selection_rationale: str = ""
    #: What the model said while it worked, as the loop captured it. Redacted
    #: on the way in like every other free text a model produced.
    model_rationale: str = ""
    offered_capabilities: Sequence[str] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One capability invocation as the caller describes it.

    ``error_class`` is separate from ``error`` because a triage asks "how did
    calls to this capability fail" and a free-text message cannot be grouped.
    """

    run_id: str
    turn_id: str
    name: str
    status: ToolCallStatus = ToolCallStatus.SUCCEEDED
    arguments: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None
    error_class: str | None = None
    evidence_ids: Sequence[str] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class RunRecorder:
    """Every write to one tenant's run traces, in one place.

    Holds a store rather than a gateway: the store already came out of a unit of
    work, so a recorder is inside its caller's transaction and a run that failed
    to commit did not half-record itself.

    ``events`` is a broker *and* the organisation this recorder is writing for,
    never a bare broker. One broker serves the whole process, so an event handed
    to it without a tenant is one the deployment-wide channel can only deliver
    to everybody — and a recorder that publishes is by definition inside a
    scoped unit of work, so the organisation is always in the caller's hand at
    the moment it decides to publish at all.
    """

    store: RunTraceStore
    guardrails: GuardrailEngine | None = None
    events: RunEventPublisher | None = None
    clock: Callable[[], datetime] = _utc_now
    ids: Callable[[], str] = _identifier

    # -- runs -----------------------------------------------------------------

    async def start_run(
        self,
        *,
        trigger: str,
        principal_id: str,
        team_node_id: str,
        run_id: str | None = None,
        alert_id: str | None = None,
        runtime: str | None = None,
        model_id: str | None = None,
        job_id: str | None = None,
        parent_run_id: str | None = None,
        objective: str = "",
        alert_labels: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentRun:
        """Record an investigation beginning and return it.

        The principal is the schedule's when a scheduler started this, and the
        person's when a human did. Recording it either way is what lets an
        approval later in the run attribute itself to somebody: a scheduled run
        is not an unattributed one.

        ``objective`` and ``alert_labels`` are redacted before either is used
        for anything, including the provisional headline computed below —
        the same defence a caller composing the request is asked to have
        already applied, repeated here because this is the one place every
        run's row is actually written. The redacted objective is what lands
        in the stored ``objective`` column, verbatim and untruncated; the
        headline computed from it is what a list shows while the run is
        still going, replaced by the delivery's own sentence when it
        completes. The raw values never reach ``AgentRun``, the headline, or
        the trace this call writes.
        """
        started = self.clock()
        redacted_objective = self._redact(objective)
        sanitized_labels = self._scrub(dict(alert_labels or {}))
        headline = synthesize_headline(
            alert_name=str(sanitized_labels.get("alertname", "")),
            resource=resource_from_labels(sanitized_labels),
            objective=redacted_objective,
        )
        attributes: dict[str, Any] = {
            RUN_METADATA_TEAM: team_node_id,
            RUN_METADATA_PRINCIPAL: principal_id,
            **dict(metadata or {}),
        }
        if job_id is not None:
            attributes[RUN_METADATA_JOB] = job_id
        if parent_run_id is not None:
            attributes[RUN_METADATA_PARENT] = parent_run_id

        run = await self.store.start_run(
            AgentRun(
                run_id=run_id or self.ids(),
                trigger=trigger,
                status=RunStatus.RUNNING,
                started_at=started,
                alert_id=alert_id,
                runtime=runtime,
                model_id=model_id,
                objective=redacted_objective,
                headline=headline,
                metadata=self._clean(attributes),
            )
        )
        await self.record_event(
            run.run_id,
            TraceEventKind.RUN_STARTED,
            payload={"trigger": trigger, RUN_METADATA_TEAM: team_node_id},
        )
        return run

    async def start_subagent_run(
        self,
        *,
        parent_run_id: str,
        objective: str,
        principal_id: str,
        team_node_id: str,
        run_id: str | None = None,
        model_id: str | None = None,
    ) -> AgentRun:
        """Record a sub-agent dispatch as its own run beneath ``parent_run_id``.

        Nested rather than folded into the parent's turns. A sub-agent's
        reasoning is exactly as worth auditing as the parent's, and a trace that
        recorded only the answer it returned would hide the part where it
        decided what to look at.
        """
        child = await self.start_run(
            trigger=TRIGGER_SUBAGENT,
            principal_id=principal_id,
            team_node_id=team_node_id,
            run_id=run_id,
            model_id=model_id,
            parent_run_id=parent_run_id,
            objective=objective,
            metadata={RUN_METADATA_SUBAGENT: True},
        )
        await self.record_event(
            parent_run_id,
            TraceEventKind.SUBAGENT_DISPATCHED,
            payload={"child_run_id": child.run_id, "objective": objective},
        )
        return child

    async def complete_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        summary: str | None = None,
        headline: str | None = None,
    ) -> AgentRun:
        """Close ``run_id`` and return the stored run.

        ``headline`` goes through the same guardrail redaction as
        ``summary`` — a sentence the model wrote is exactly as capable of
        carrying a secret as the document it summarises.
        """
        finished = self.clock()
        closed = await self.store.complete_run(
            run_id,
            status=status,
            finished_at=finished,
            summary=self._redact(summary) if summary is not None else None,
            headline=self._redact(headline) if headline is not None else None,
        )
        await self.record_event(
            run_id,
            TraceEventKind.RUN_FINISHED,
            payload={"status": status.value},
        )
        return closed

    async def record_attention(self, run_id: str, attention: Attention) -> TraceEventRecord:
        """Record that ``run_id`` started or stopped waiting on a person.

        Written as an event rather than onto the run, because the run row is
        written twice — once at the start and once at the end — and an
        investigation blocks and unblocks several times in between. A field
        would record only the state the run happened to be in when it finished,
        which for a run that concluded is always "waiting on nobody".
        """
        return await self.record_event(
            run_id,
            TraceEventKind.ATTENTION_CHANGED,
            payload={
                RUN_ATTENTION_KEY: attention.state.value,
                RUN_ATTENTION_SINCE_KEY: (
                    attention.waiting_since.isoformat() if attention.waiting_since else ""
                ),
                "questions": attention.questions,
                "approvals": attention.approvals,
                "summary": attention.summary,
            },
        )

    async def mark_interrupted(self, run_id: str, *, reason: str) -> AgentRun:
        """Close ``run_id`` as interrupted, keeping whatever was captured.

        The reason is stored on the run rather than only in the log, because
        this is the status an operator meets in a list and "interrupted" on its
        own does not say whether the replica died, the lease expired, or the
        process was told to stop.
        """
        run = await self.store.get_run(run_id)
        finished = self.clock()
        metadata = {**(dict(run.metadata) if run else {}), RUN_METADATA_INTERRUPTION: reason}

        # The event first: the store's ``complete_run`` cannot carry metadata,
        # so an interrupted run's reason reaches the log whatever happens to the
        # summary write below.
        await self.record_event(run_id, TraceEventKind.RUN_INTERRUPTED, payload={"reason": reason})
        closed = await self.store.complete_run(
            run_id,
            status=RunStatus.INTERRUPTED,
            finished_at=finished,
            summary=(run.summary if run and run.summary else None),
        )
        logger.warning("runs.interrupted", run_id=run_id, reason=reason)
        # Returned with the reason attached even though the store's terminal
        # write does not carry metadata: the caller asked what it recorded.
        return AgentRun(
            run_id=closed.run_id,
            trigger=closed.trigger,
            status=closed.status,
            started_at=closed.started_at,
            finished_at=closed.finished_at,
            alert_id=closed.alert_id,
            runtime=closed.runtime,
            model_id=closed.model_id,
            summary=closed.summary,
            headline=closed.headline,
            metadata=metadata,
        )

    # -- turns, calls, evidence -----------------------------------------------

    async def record_turn(self, turn: RecordedTurn) -> TurnRecord:
        """Store one iteration of the loop and return the record written."""
        payload, _ = truncate(
            {
                **self._scrub(turn.payload),
                TURN_PAYLOAD_RATIONALE: self._redact(turn.selection_rationale),
                TURN_PAYLOAD_MODEL_RATIONALE: self._redact(turn.model_rationale),
                TURN_PAYLOAD_CAPABILITIES: list(turn.offered_capabilities),
            }
        )
        usage: dict[str, Any] = {
            TURN_USAGE_MODEL: turn.model,
            TURN_USAGE_PROMPT_TOKENS: turn.prompt_tokens,
            TURN_USAGE_COMPLETION_TOKENS: turn.completion_tokens,
            TURN_USAGE_DURATION_MS: turn.duration_ms,
        }
        # The key itself is absent for an unpriced turn — never present with a
        # fabricated ``0.0`` standing in for "the provider publishes no price".
        if turn.cost is not None:
            usage[TURN_USAGE_COST] = turn.cost
        record = await self.store.record_turn(
            TurnRecord(
                turn_id=self.ids(),
                run_id=turn.run_id,
                index=turn.index,
                started_at=turn.started_at,
                finished_at=turn.finished_at,
                payload=payload,
                usage=usage,
            )
        )
        await self.record_event(
            turn.run_id,
            TraceEventKind.TURN_COMPLETED,
            turn_id=record.turn_id,
            payload={"index": turn.index, TURN_USAGE_MODEL: turn.model},
        )
        return record

    async def record_stage(
        self,
        run_id: str,
        *,
        stage: str,
        finding: str = "",
        duration_ms: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        llm_calls: int = 0,
        failed: bool = False,
    ) -> TraceEventRecord:
        """Record that one of the six stages finished, and what it did.

        An event rather than a table of its own. A stage has no body worth a
        row — a name, a line, a duration and a spend — and the event log is
        already the thing a replay orders everything else by, so a stage
        written here arrives in the same sequence as the turns that happened
        inside it rather than needing a timestamp comparison to be placed.

        Written on the stage *ending*, so a run that stopped inside a stage
        leaves that stage unrecorded. That is the honest asymmetry: the trace
        then says which stages finished, and never claims one completed on the
        strength of having been seen to start.

        ``finding`` goes through redaction like every other free text, because
        it is assembled from what a model classified and what a delivery
        reported, and both can carry an identifier a ruleset removes.
        """
        return await self.record_event(
            run_id,
            TraceEventKind.STAGE_COMPLETED,
            payload={
                STAGE_EVENT_NAME: stage,
                STAGE_DETAIL_FINDING: self._redact(finding),
                STAGE_EVENT_DURATION_MS: duration_ms,
                STAGE_DETAIL_PROMPT_TOKENS: prompt_tokens,
                STAGE_DETAIL_COMPLETION_TOKENS: completion_tokens,
                STAGE_DETAIL_LLM_CALLS: llm_calls,
                STAGE_EVENT_FAILED: failed,
            },
        )

    async def record_call(self, call: RecordedCall) -> ToolCallRecord:
        """Store one capability invocation and return the record written.

        The result is stored in the call's arguments payload under ``result``
        rather than in a column of its own, because the port keeps one JSONB
        body per call and splitting it would mean two bounds to keep in step.
        """
        arguments, _ = truncate(
            {
                "arguments": self._scrub(call.arguments),
                "result": self._scrub(call.result),
                "duration_ms": call.duration_ms,
                "error_class": call.error_class,
            }
        )
        record = await self.store.record_tool_call(
            ToolCallRecord(
                call_id=self.ids(),
                run_id=call.run_id,
                turn_id=call.turn_id,
                tool_name=call.name,
                status=call.status,
                arguments=arguments,
                started_at=call.started_at,
                finished_at=call.finished_at,
                error=self._redact(call.error) if call.error is not None else None,
                evidence_ids=tuple(call.evidence_ids),
            )
        )
        await self.record_event(
            call.run_id,
            TraceEventKind.CAPABILITY_CALLED,
            turn_id=call.turn_id,
            payload={
                "capability": call.name,
                "status": call.status.value,
                "error_class": call.error_class,
            },
        )
        return record

    async def record_evidence(
        self,
        *,
        run_id: str,
        source: str,
        evidence_type: str,
        body: Mapping[str, Any],
        evidence_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> EvidenceRecord:
        """Store one observation and return the record written."""
        scrubbed, _ = truncate(self._scrub(body))
        record = await self.store.record_evidence(
            EvidenceRecord(
                evidence_id=evidence_id or self.ids(),
                run_id=run_id,
                source=source,
                evidence_type=evidence_type,
                observed_at=observed_at or self.clock(),
                body=scrubbed,
            )
        )
        await self.record_event(
            run_id,
            TraceEventKind.EVIDENCE_OBSERVED,
            payload={"evidence_id": record.evidence_id, "source": source},
        )
        return record

    # -- the log --------------------------------------------------------------

    async def record_event(
        self,
        run_id: str,
        kind: TraceEventKind,
        *,
        payload: Mapping[str, Any] | None = None,
        turn_id: str | None = None,
    ) -> TraceEventRecord:
        """Append one event to ``run_id``'s log and publish it.

        In that order, and the order is the design. An event published before it
        was logged is an event a reconnecting client cannot be given again,
        which is the exactly-once guarantee gone for the sake of a few
        microseconds.
        """
        body, _ = truncate(self._scrub(payload or {}))
        record = await self.store.record_event(
            TraceEventRecord(
                event_id=self.ids(),
                run_id=run_id,
                kind=kind.value,
                occurred_at=self.clock(),
                turn_id=turn_id,
                payload=body,
            )
        )
        if self.events is not None:
            await self.events.publish(RunEvent.of(record))
        return record

    async def record_guardrail_action(
        self, run_id: str, *, kind: str, target: str, reason: str
    ) -> TraceEventRecord:
        """Record that a guardrail changed what this run was allowed to do."""
        return await self.record_event(
            run_id,
            TraceEventKind.GUARDRAIL_ACTION,
            payload={"action": kind, "target": target, "reason": reason},
        )

    async def record_masking(
        self, run_id: str, *, detector: str, occurrences: int
    ) -> TraceEventRecord:
        """Record that identifiers were tokenised on their way to a model.

        The detector and the count, never the values. A trace event that named
        what was masked would be the leak the masking exists to prevent.
        """
        return await self.record_event(
            run_id,
            TraceEventKind.MASKING_APPLIED,
            payload={"detector": detector, "occurrences": occurrences},
        )

    async def record_budget_eviction(
        self, run_id: str, *, evicted: Iterable[str], reason: str
    ) -> TraceEventRecord:
        """Record what the context budget dropped, and why."""
        return await self.record_event(
            run_id,
            TraceEventKind.BUDGET_EVICTION,
            payload={"evicted": list(evicted), "reason": reason},
        )

    # -- guardrails -----------------------------------------------------------

    def _redact(self, text: str | None) -> str:
        """Return ``text`` with anything the ruleset matches already removed."""
        if not text:
            return text or ""
        if self.guardrails is None:
            return text
        return self.guardrails.scan(text).text

    def _scrub(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return ``payload`` with every string, at any depth, scanned.

        A schema-aware pass would miss the field somebody adds next week, which
        is the field a leak uses precisely because nobody is looking at it.
        """
        if self.guardrails is None:
            return dict(payload)
        return {key: self._scrub_value(value) for key, value in payload.items()}

    def _scrub_value(self, value: Any) -> Any:
        """Return one value with every string inside it scanned."""
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, Mapping):
            return {key: self._scrub_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self._scrub_value(item) for item in value]
        return value

    def _clean(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Return run metadata with its string values scanned."""
        return self._scrub(metadata)


__all__ = ["RecordedCall", "RecordedTurn", "RunRecorder"]
