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
from datetime import timedelta
from typing import Any

from core.agent.session import EvidenceEntry, Session
from core.agent.turn import Turn
from core.capability.telemetry import InvocationOutcome
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports.run_trace_store import ToolCallStatus
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.runs.headline import report_body
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from platform.runs.stream import RunEventBroker


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


@dataclass(slots=True)
class RunTraceRecordingHook:
    """Writes what one investigation did, as it happens, through ``RunRecorder``.

    One instance per investigation — the same granularity
    ``ReActInvestigationRunner`` already composes a loop at — so the run id
    this hook writes under is never in question.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    run_id: str
    guardrails: GuardrailEngine | None = field(default=None)
    broker: RunEventBroker | None = field(default=None)

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
                store=uow.run_traces, guardrails=self.guardrails, broker=self.broker
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
        )


__all__ = ["RunTraceRecordingHook"]
