"""Saying that the context is filling up, on the turn before it costs anything.

The context budget itself runs inside the loop; this hook does not enforce
anything. It reports — and it reports early on purpose. By the time an eviction
appears in a turn record, the run has already lost evidence, and the useful
moment to tell an operator was the turn before that.

The warning threshold is a constant rather than a literal because the right
value depends on how large a single tool result tends to be in a deployment, and
that is exactly the kind of thing somebody tunes once and should be able to find.
"""

from __future__ import annotations

from config.constants.investigation import (
    CONTEXT_BUDGET_WARNING_RATIO,
    CONTEXT_EVIDENCE_BUDGET_RATIO,
)
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from core.agent.turn import Turn
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: After accounting: this reads the state the loop has already settled.
BUDGET_ORDER = -100


def utilisation(session: Session) -> float:
    """Return the share of the evidence budget currently in use.

    ``0.0`` when the session is running with no budget of its own, which is not
    the same as "empty" and is why this returns a share rather than a verdict.
    """
    if session.context_budget_tokens <= 0:
        return 0.0
    allowed = session.context_budget_tokens * CONTEXT_EVIDENCE_BUDGET_RATIO
    if allowed <= 0:
        return 1.0
    return session.evidence_tokens / allowed


async def report_budget(session: Session, turn: Turn) -> None:
    """Log how full the context is, warning once it is nearly spent."""
    if session.context_budget_tokens <= 0:
        return

    share = utilisation(session)
    event = "agent.context_budget"
    fields = {
        "session_id": session.id,
        "iteration": turn.index,
        "evidence_entries": len(session.evidence),
        "evidence_tokens": session.evidence_tokens,
        "budget_tokens": session.context_budget_tokens,
        "utilisation": round(share, 3),
        "actions_this_turn": len(turn.budget_actions),
    }

    if share >= CONTEXT_BUDGET_WARNING_RATIO:
        logger.warning(event, **fields)
    else:
        logger.info(event, **fields)


def register(hooks: HookRegistry, *, order: int = BUDGET_ORDER) -> None:
    """Attach the budget report at the turn boundary."""
    hooks.register(HookPoint.ON_TURN_END, report_budget, name="budget", order=order)


__all__ = [
    "BUDGET_ORDER",
    "register",
    "report_budget",
    "utilisation",
]
