"""Counting, per turn, what the model cost the run in attempts.

Every repair, compaction and truncation is already a line in the trace. This
turns the same lines into numbers, so the question "is this model costing me
throughput" has an answer on a dashboard rather than one somebody reconstructs by
reading traces.

Not a default hook. It needs a metric registry, and a registry is a deployment's
to build — the built-in three take nothing. A deployment that has one registers
this beside them and gets the model family populated; one that has not is
unaffected, which is the same arrangement the cost ledger already has.
"""

from __future__ import annotations

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from core.agent.turn import Turn
from platform.observability.metrics.definitions import MetricRegistry
from platform.observability.metrics.model_behaviour import record_turn

#: After accounting, because what a turn cost in money and what it cost in
#: attempts read together and this is the second half of that sentence.
MODEL_BEHAVIOUR_ORDER = -400


def register(
    hooks: HookRegistry, metrics: MetricRegistry, *, order: int = MODEL_BEHAVIOUR_ORDER
) -> None:
    """Attach the model-behaviour counters at the turn boundary."""

    async def count_turn(session: Session, turn: Turn) -> None:
        """Count everything this turn had to do to the model's output."""
        record_turn(metrics, turn)

    hooks.register(HookPoint.ON_TURN_END, count_turn, name="model_behaviour", order=order)


__all__ = ["MODEL_BEHAVIOUR_ORDER", "register"]
