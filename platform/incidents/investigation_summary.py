"""The three numbers a person reads about one investigation, and when to omit them.

``duration_seconds`` and ``cost_usd`` are read from the run, never recalculated
here. A run still in flight has a start and no end, and a run whose provider
never reported a price has nothing to sum — both are reported as absent rather
than as a fabricated zero, the same convention ``core.llm.usage.UsageRecord``
already uses for an unpriced call: an unknown cost is worse to hide than to
show as unknown, because a total that looks authoritative and is wrong is the
one an operator stops questioning.

``step_count`` gets no such treatment: a run that has taken no turns yet has
taken zero turns, which is a fact worth showing exactly as it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from config.constants.runs import TURN_USAGE_COST
from platform.persistence.ports.run_trace_store import AgentRun, TurnRecord


@dataclass(frozen=True, slots=True)
class InvestigationSummary:
    """The step count, duration and cost one investigation accounts for."""

    step_count: int
    #: Seconds from the run's start to its end. ``None`` while the run has
    #: not finished — there is no end yet, not a zero-length one.
    duration_seconds: float | None = None
    #: US dollars, summed from the turns that actually carry a priced figure.
    #: ``None`` when none of them do, rather than a total that looks like it
    #: knows the run was free.
    cost_usd: float | None = None


def summarise_investigation(run: AgentRun, turns: Sequence[TurnRecord]) -> InvestigationSummary:
    """Return what ``run`` and its ``turns`` account for, omission included."""
    duration: float | None = None
    if run.started_at is not None and run.finished_at is not None:
        duration = (run.finished_at - run.started_at).total_seconds()

    priced = [cost for turn in turns if (cost := turn.usage.get(TURN_USAGE_COST)) is not None]
    cost = sum(float(value) for value in priced) if priced else None

    return InvestigationSummary(
        step_count=len(turns),
        duration_seconds=duration,
        cost_usd=cost,
    )


__all__ = ["InvestigationSummary", "summarise_investigation"]
