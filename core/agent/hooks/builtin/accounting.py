"""Running totals, and the part of them nobody could price.

The session's ledger already holds every model call. What this adds is the
running report — after each turn and once at the end — and it reports the
unpriced share alongside the total every time.

That pairing is the whole point. ``UsageLedger.cost_usd`` is a floor rather than
a total: a locally hosted model has no published price, and a run that made
three calls to one would otherwise report a cost that reads as authoritative and
is wrong. An operator seeing "$0.04 across 6 calls, 3 unpriced" knows exactly
what they are looking at.
"""

from __future__ import annotations

from typing import Any

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from core.agent.turn import Turn
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: After tracing, before anything that might act on a budget.
ACCOUNTING_ORDER = -500


async def account_turn_end(session: Session, turn: Turn) -> None:
    """Log the run's totals as of this turn."""
    tokens = session.usage.tokens
    logger.info(
        "agent.usage_after_turn",
        session_id=session.id,
        iteration=turn.index,
        turn_tokens=turn.usage.tokens.total_tokens if turn.usage else 0,
        run_input_tokens=tokens.total_input_tokens,
        run_output_tokens=tokens.output_tokens,
        estimated=tokens.estimated,
    )


async def account_run_end(session: Session, result: Any) -> None:
    """Log the run's final totals, priced and unpriced."""
    tokens = session.usage.tokens
    logger.info(
        "agent.usage_total",
        session_id=session.id,
        model_calls=session.usage.call_count,
        input_tokens=tokens.total_input_tokens,
        output_tokens=tokens.output_tokens,
        cost_usd_floor=round(session.usage.cost_usd, 6),
        unpriced_calls=session.usage.unpriced_call_count,
        complete=session.usage.is_complete,
    )


def register(hooks: HookRegistry, *, order: int = ACCOUNTING_ORDER) -> None:
    """Attach the accounting hook at the turn and run boundaries."""
    hooks.register(HookPoint.ON_TURN_END, account_turn_end, name="accounting", order=order)
    hooks.register(HookPoint.ON_RUN_END, account_run_end, name="accounting", order=order)


__all__ = [
    "ACCOUNTING_ORDER",
    "account_run_end",
    "account_turn_end",
    "register",
]
