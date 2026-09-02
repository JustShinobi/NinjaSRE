"""Translating what the canonical loop produced into what the recorder stores.

``RunTraceRecordingHook`` is registered on ``on_turn_end`` — the one point
the loop calls once per iteration, with the whole turn already assembled
(``core.agent.hooks.types.TurnEndHook``). It does not invent anything the
loop did not already produce: a turn's usage, its calls, and the evidence
those calls produced are all read off ``Turn`` and ``Session`` exactly as
built.

One unit of work per turn, opened and closed inside this hook, because an
investigation lives minutes and a transaction does not — the same reason
``gateway/http/orchestration.py``'s own writes never hold one open across a
call to the model or a capability.

A write that fails here is a hook that raised. ``core.agent.hooks.registry``
already treats a raising hook as a recorded failure rather than a crash:
this module adds no defensive handling of its own, because doing so would
either duplicate that behaviour or, done carelessly, swallow an error the
registry was built to keep visible on the turn it happened during.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from config.constants.runs import (
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
    TURN_PAYLOAD_STAGE,
)
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import Turn
from core.capability.telemetry import InvocationOutcome
from core.pipeline.streaming import PipelineEvent, PipelineEventKind
from core.state.types import StageName
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports.run_trace_store import ToolCallStatus
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.runs.headline import report_body
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from platform.runs.stream import RunEventBroker, RunEventPublisher


def _status_of(*, denied: bool, outcome: InvocationOutcome) -> ToolCallStatus:
    """Return the stored status for one call, denial taking precedence.

    A denial is neither an absence nor a plain failure: it is its
    own status, so a reviewer reading the trace can tell "the model tried
    and a policy said no" from "the model tried and it broke".
    """
    if denied:
        return ToolCallStatus.DENIED
    return (
        ToolCallStatus.SUCCEEDED if outcome is InvocationOutcome.SUCCESS else ToolCallStatus.FAILED
    )


def _result_of(entries: list[EvidenceEntry]) -> Mapping[str, Any]:
    """Return the stored ``result`` body for one call, from its own evidence.

    Every entry a call produced carries that call's full rendered result in
    ``content`` (``core.agent.execution.execute_call`` sets it once and
    passes it to every entry the call drafted), so the first entry already
    holds it. A call with no evidence — denied, failed, or a cache replay —
    has nothing here; its outcome and its error carry what happened instead.
    """
    if not entries:
        return {}
    return {"content": entries[0].content}


def _counted(value: str | None) -> int:
    """Return a number the pipeline put on a stage's detail, or nought.

    The stream's detail is a string-to-string mapping, so every count crosses
    it as text. Anything unreadable counts as nothing rather than raising: a
    malformed detail should cost a stage its token line, never the run its
    trace.
    """
    try:
        return int(value or 0)
    except ValueError:
        return 0


@dataclass(slots=True)
class RunTraceRecordingHook:
    """Writes what one investigation did, as it happens, through ``RunRecorder``.

    One instance per investigation — the same granularity
    ``ReActInvestigationRunner`` already composes a loop at — so the run id
    this hook writes under is never in question.

    It is registered at two points, on two different channels, and the pairing
    is the whole reason a trace can be read by stage.

    ``on_turn_end`` is the loop's, once per iteration, and the loop knows
    nothing about stages. ``emit`` is the *pipeline's*: this is an
    ``EventSink`` on the stream the pipeline announces ``stage_start`` and
    ``stage_end`` on. A pipeline runs its stages strictly in order over one
    run, and this object belongs to that one run, so the stage that is open
    when a turn ends is the stage the turn belonged to. Read, not inferred —
    and it stays true if the stage list ever changes, which is what a
    heuristic over turn indices or capability names would not.

    A caller that composes no stream still records everything it recorded
    before. Turns then carry no stage, which is the honest answer for a loop
    that ran under none of the six.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    run_id: str
    guardrails: GuardrailEngine | None = field(default=None)
    broker: RunEventBroker | None = field(default=None)
    #: The stage the pipeline currently has open, and when it opened. Mutable
    #: and unguarded because a pipeline's stages are sequential and this object
    #: serves exactly one of them at a time; a hook shared between runs would
    #: be wrong for reasons that start well before this field.
    _stage: StageName | None = field(default=None, init=False)
    _stage_started_at: datetime | None = field(default=None, init=False)

    def _events(self) -> RunEventPublisher | None:
        """Return where this hook publishes, and whose runs those are.

        ``None`` when nothing was composed to publish to — a hook that records
        with nobody watching. The organisation is this hook's own scope, the
        same one every unit of work it opens is opened for, because a run
        broker is process-wide and an event handed to it without a tenant is
        one the deployment-wide channel can only deliver to everybody.
        """
        if self.broker is None:
            return None
        return RunEventPublisher(broker=self.broker, org_id=self.scope.org_id)

    async def emit(self, event: PipelineEvent) -> None:
        """Follow the pipeline's stage boundaries, and write a record at each end.

        The only three kinds that mean anything here. Everything else on the
        stream — thoughts, tool calls, the result — already reaches the trace
        through the loop's own hooks, and taking it twice would double every
        call in the record.

        A stage that failed is recorded from the ``error`` event rather than
        from a ``stage_end`` that never arrives: the lifecycle emits one and
        not the other, and a stage that raised is exactly the stage somebody
        opens the trace to read about.
        """
        match event.kind:
            case PipelineEventKind.STAGE_START if event.stage is not None:
                self._stage = event.stage
                self._stage_started_at = event.occurred_at
            case PipelineEventKind.STAGE_END if event.stage is not None:
                await self._write_stage(event, failed=False)
            case PipelineEventKind.ERROR if event.stage is not None:
                await self._write_stage(event, failed=True)
            case _:
                return

    async def _write_stage(self, event: PipelineEvent, *, failed: bool) -> None:
        """Record the stage ``event`` closes, and forget it was open."""
        detail = event.detail
        finding = detail.get(STAGE_DETAIL_FINDING, "") or (event.text if failed else "")
        async with self.gateway.begin(self.scope) as uow:
            await RunRecorder(
                store=uow.run_traces, guardrails=self.guardrails, events=self._events()
            ).record_stage(
                self.run_id,
                stage=event.stage.value if event.stage is not None else "",
                finding=finding,
                duration_ms=self._elapsed_to(event.occurred_at),
                prompt_tokens=_counted(detail.get(STAGE_DETAIL_PROMPT_TOKENS)),
                completion_tokens=_counted(detail.get(STAGE_DETAIL_COMPLETION_TOKENS)),
                llm_calls=_counted(detail.get(STAGE_DETAIL_LLM_CALLS)),
                failed=failed,
            )
        self._stage = None
        self._stage_started_at = None

    def _elapsed_to(self, ended_at: datetime) -> int:
        """Return how long the open stage ran, in milliseconds, or nought.

        Nought when no start was seen — a hook attached to a stream mid-run, or
        a caller emitting an end on its own. A duration invented from the two
        events that did arrive would be a measurement of the wrong interval.
        """
        if self._stage_started_at is None:
            return 0
        return int((ended_at - self._stage_started_at).total_seconds() * 1_000)

    async def on_turn_end(self, session: Session, turn: Turn) -> None:
        """Record ``turn``, its calls, and the evidence they produced.

        A no-op for a sub-agent's session (``session.subagent`` is set): a
        child is a nested run of its own, and folding its turns into the
        parent's trace would be the parent's record absorbing the child's —
        exactly what the sub-agent edge case in the spec forbids.
        """
        if session.subagent:
            return

        async with self.gateway.begin(self.scope) as uow:
            recorder = RunRecorder(
                store=uow.run_traces, guardrails=self.guardrails, events=self._events()
            )
            recorded_turn = await recorder.record_turn(self._recorded_turn(turn))

            call_ids = {execution.call_id for execution in turn.executions}
            evidence_by_call: dict[str, list[EvidenceEntry]] = {}
            for entry in session.evidence:
                if entry.call_id in call_ids:
                    evidence_by_call.setdefault(entry.call_id, []).append(entry)

            for execution in turn.executions:
                entries = evidence_by_call.get(execution.call_id, [])
                await recorder.record_call(
                    RecordedCall(
                        run_id=self.run_id,
                        turn_id=recorded_turn.turn_id,
                        name=execution.capability,
                        status=_status_of(denied=execution.denied, outcome=execution.outcome),
                        arguments=execution.arguments,
                        result=_result_of(entries),
                        duration_ms=int(execution.duration_seconds * 1_000),
                        error=execution.error_message or None,
                        error_class=execution.error_class.value if execution.error_class else None,
                        evidence_ids=execution.evidence_ids,
                    )
                )
                for entry in entries:
                    await recorder.record_evidence(
                        run_id=self.run_id,
                        source=entry.source,
                        evidence_type=entry.evidence_type.value,
                        body={
                            "summary": entry.summary,
                            "content": entry.content,
                            "reference": entry.reference,
                            "capability": entry.capability,
                        },
                        evidence_id=entry.id,
                    )

    def _recorded_turn(self, turn: Turn) -> RecordedTurn:
        """Return ``turn`` translated into the recorder's own vocabulary."""
        usage = turn.usage
        tokens = usage.tokens if usage is not None else None
        finished_at = (
            turn.started_at + timedelta(seconds=turn.duration_seconds)
            if turn.started_at is not None
            else None
        )
        return RecordedTurn(
            run_id=self.run_id,
            index=turn.index,
            model=turn.model_id,
            prompt_tokens=tokens.total_input_tokens if tokens is not None else 0,
            completion_tokens=tokens.output_tokens if tokens is not None else 0,
            cost=usage.cost_usd if usage is not None else None,
            duration_ms=int(turn.duration_seconds * 1_000),
            selection_rationale=turn.selection_rationale,
            # The marker line goes here for the same reason it goes from the
            # summary: it is a control line the delivery protocol asked the
            # model to write, the deployment consumed it to name the run, and
            # leaving it in put the run's own title back on the page one panel
            # below the heading that already carries it.
            model_rationale=report_body(turn.rationale),
            offered_capabilities=turn.offered_capabilities,
            started_at=turn.started_at,
            finished_at=finished_at,
            # The stage the pipeline had open when this turn ended. Absent
            # rather than defaulted for a loop nobody drove through a pipeline:
            # a sub-agent's own run and a bare loop belong to none of the six,
            # and naming one of them would be a stage this turn never ran in.
            payload=({TURN_PAYLOAD_STAGE: self._stage.value} if self._stage is not None else {}),
        )


__all__ = ["RunTraceRecordingHook"]
