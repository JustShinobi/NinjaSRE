"""Turning what the loop recorded into what a surface watches.

The runtime records turns; the pipeline emits events. This is the translation,
and keeping it in one function rather than inlining it in the gathering stage
buys the property that matters: it can be attached as an ``on_turn_end`` hook,
in which case the events reach a console *while* the run is happening, or run
over ``RunResult.turns`` afterwards, in which case they reach a store. Both
produce the same events in the same order, so what a console showed live and
what a trace replays are the same investigation.

A replayed call still emits its lifecycle. The model asked for it, the loop
answered from cache, and a stream that hid that would show a run doing less
work than the trajectory scorer thinks it did.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.agent.subagents.dispatch import DISPATCH_CAPABILITY
from core.agent.turn import ToolExecution, Turn
from core.capability.telemetry import InvocationOutcome
from core.pipeline.streaming import PipelineEvent, PipelineEventKind
from core.state.types import StageName

#: What a ``tool_end`` says when the loop answered from its duplicate cache.
REPLAYED_SUMMARY = "already held — the loop answered this call from its own cache"

#: What it says when a hook refused the call.
DENIED_SUMMARY = "refused before it ran: {reason}"


def events_for_turn(
    turn: Turn, *, stage: StageName = StageName.GATHER_EVIDENCE
) -> tuple[PipelineEvent, ...]:
    """Return the events one completed turn produced, in the order they happened."""
    events: list[PipelineEvent] = []

    if turn.rationale.strip():
        events.append(
            PipelineEvent(kind=PipelineEventKind.THOUGHT, stage=stage, text=turn.rationale)
        )

    for execution in turn.executions:
        events.extend(_events_for_execution(execution, stage=stage))

    return tuple(events)


def events_for_turns(
    turns: Sequence[Turn], *, stage: StageName = StageName.GATHER_EVIDENCE
) -> tuple[PipelineEvent, ...]:
    """Return the events a whole run produced, in order."""
    return tuple(event for turn in turns for event in events_for_turn(turn, stage=stage))


def _events_for_execution(
    execution: ToolExecution, *, stage: StageName
) -> tuple[PipelineEvent, ...]:
    """Return the lifecycle of one capability call, sub-agent dispatch included."""
    if execution.capability == DISPATCH_CAPABILITY:
        return _subagent_events(execution, stage=stage)

    failed = execution.denied or execution.outcome is not InvocationOutcome.SUCCESS
    return (
        PipelineEvent(
            kind=PipelineEventKind.TOOL_START,
            stage=stage,
            capability=execution.capability,
            call_id=execution.call_id,
            detail={key: str(value) for key, value in execution.arguments.items()},
        ),
        PipelineEvent(
            kind=PipelineEventKind.TOOL_END,
            stage=stage,
            capability=execution.capability,
            call_id=execution.call_id,
            failed=failed,
            text=_summary(execution),
        ),
        *(
            PipelineEvent(
                kind=PipelineEventKind.EVIDENCE,
                stage=stage,
                capability=execution.capability,
                call_id=execution.call_id,
                evidence_id=evidence_id,
            )
            for evidence_id in execution.evidence_ids
        ),
    )


def _subagent_events(execution: ToolExecution, *, stage: StageName) -> tuple[PipelineEvent, ...]:
    """Return the lifecycle of one specialist dispatch.

    The specialist's name comes from the dispatch arguments, because that is
    where the parent named it. A dispatch whose arguments did not survive is
    still emitted, unnamed, rather than dropped: a hole in the trace nobody can
    see is the one nobody finds.
    """
    name = str(execution.arguments.get("subagent") or execution.arguments.get("name") or "")
    return (
        PipelineEvent(
            kind=PipelineEventKind.SUBAGENT_START,
            stage=stage,
            subagent=name,
            call_id=execution.call_id,
        ),
        PipelineEvent(
            kind=PipelineEventKind.SUBAGENT_END,
            stage=stage,
            subagent=name,
            call_id=execution.call_id,
            failed=execution.outcome is not InvocationOutcome.SUCCESS,
            text=_summary(execution),
        ),
    )


def _summary(execution: ToolExecution) -> str:
    """Return one line describing how this call ended."""
    if execution.denied:
        return DENIED_SUMMARY.format(reason=execution.error_message or "no reason recorded")
    if execution.replayed:
        return REPLAYED_SUMMARY
    if execution.error_message:
        return execution.error_message
    return f"{len(execution.evidence_ids)} evidence entry/entries recorded"


__all__ = [
    "DENIED_SUMMARY",
    "REPLAYED_SUMMARY",
    "events_for_turn",
    "events_for_turns",
]
