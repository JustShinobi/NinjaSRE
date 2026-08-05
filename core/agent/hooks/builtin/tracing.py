"""The hook that makes a run visible while it is happening.

The turn records are the durable trace and they are written as the run goes, but
they are read afterwards. An operator watching an investigation that is going
wrong right now needs a stream, and a structured log line per lifecycle point is
what the console, the SSE surface, and a terminal ``tail`` all read.

Deliberately observe-only, and deliberately cheap: identifiers and counts, never
payloads. A tracing hook that logged tool arguments would put evidence — and
one day a value the masking layer had not seen yet — into a second store nobody
audits.
"""

from __future__ import annotations

from typing import Any

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint, ToolContext
from core.agent.session import Session
from core.agent.turn import Turn
from core.capability.result import CapabilityResult
from core.llm.types import ToolCall
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Runs before anything that might record against the run, so a failure in a
#: later hook still has a start line to be read against.
TRACING_ORDER = -1_000


async def trace_run_start(session: Session) -> None:
    """Log the start of a run."""
    logger.info(
        "agent.run_started",
        session_id=session.id,
        depth=session.depth,
        subagent=session.subagent,
        alert_source=session.alert_source,
        max_iterations=session.max_iterations,
    )


async def trace_pre_tool_use(call: ToolCall, context: ToolContext) -> None:
    """Log a capability about to run."""
    logger.info(
        "agent.tool_called",
        session_id=context.session.id,
        iteration=context.iteration,
        capability=call.name,
        side_effect_level=context.registered.metadata.side_effect_level.value,
    )


async def trace_post_tool_use(
    call: ToolCall, result: CapabilityResult, context: ToolContext
) -> None:
    """Log what a capability returned, by classification rather than by value."""
    logger.info(
        "agent.tool_returned",
        session_id=context.session.id,
        iteration=context.iteration,
        capability=call.name,
        succeeded=result.succeeded,
        error_class=result.error.classification.value if result.error else None,
        evidence=len(result.evidence),
    )


async def trace_turn_end(session: Session, turn: Turn) -> None:
    """Log one completed iteration."""
    logger.info(
        "agent.turn_completed",
        session_id=session.id,
        iteration=turn.index,
        offered=len(turn.offered_capabilities),
        called=len(turn.executions),
        fresh_evidence=turn.produced_fresh_evidence,
        guardrails=[action.kind.value for action in turn.guardrail_actions],
        duration_seconds=round(turn.duration_seconds, 3),
    )


async def trace_run_end(session: Session, result: Any) -> None:
    """Log the end of a run and what it cost."""
    logger.info(
        "agent.run_ended",
        session_id=session.id,
        status=session.status.value,
        iterations=session.iteration,
        evidence=len(session.evidence),
        model_calls=session.usage.call_count,
        unpriced_calls=session.usage.unpriced_call_count,
    )


async def trace_cancel(session: Session) -> None:
    """Log a run that stopped because someone asked it to."""
    logger.info("agent.run_cancelled", session_id=session.id, iteration=session.iteration)


def register(hooks: HookRegistry, *, order: int = TRACING_ORDER) -> None:
    """Attach the tracing hook at every lifecycle point."""
    hooks.register(HookPoint.ON_RUN_START, trace_run_start, name="tracing", order=order)
    hooks.register(HookPoint.PRE_TOOL_USE, trace_pre_tool_use, name="tracing", order=order)
    hooks.register(HookPoint.POST_TOOL_USE, trace_post_tool_use, name="tracing", order=order)
    hooks.register(HookPoint.ON_TURN_END, trace_turn_end, name="tracing", order=order)
    hooks.register(HookPoint.ON_RUN_END, trace_run_end, name="tracing", order=order)
    hooks.register(HookPoint.ON_CANCEL, trace_cancel, name="tracing", order=order)


__all__ = [
    "TRACING_ORDER",
    "register",
    "trace_cancel",
    "trace_post_tool_use",
    "trace_pre_tool_use",
    "trace_run_end",
    "trace_run_start",
    "trace_turn_end",
]
