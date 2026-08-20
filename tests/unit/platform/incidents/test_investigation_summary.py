"""What one investigation's headline numbers are, and what they are not.

``duration_seconds`` and ``cost_usd`` are ``None`` when the underlying facts
are not yet known — never a fabricated zero. ``step_count`` is always a real
count, zero included, because a run that took no turns yet is a fact, not an
absence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.runs import TURN_USAGE_COST
from platform.incidents.investigation_summary import (
    InvestigationSummary,
    summarise_investigation,
)
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, TurnRecord

pytestmark = pytest.mark.unit

STARTED = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _run(*, finished: datetime | None = None) -> AgentRun:
    return AgentRun(
        run_id="run-1",
        trigger="alert",
        status=RunStatus.COMPLETED if finished else RunStatus.RUNNING,
        started_at=STARTED,
        finished_at=finished,
    )


def _turn(index: int, *, cost: float | None = None) -> TurnRecord:
    usage: dict[str, object] = {}
    if cost is not None:
        usage[TURN_USAGE_COST] = cost
    return TurnRecord(turn_id=f"turn-{index}", run_id="run-1", index=index, usage=usage)


def test_step_count_is_the_number_of_turns_zero_included() -> None:
    summary = summarise_investigation(_run(), turns=())

    assert summary.step_count == 0


def test_step_count_counts_every_turn_recorded() -> None:
    summary = summarise_investigation(_run(), turns=(_turn(0), _turn(1), _turn(2)))

    assert summary.step_count == 3


def test_duration_is_the_span_from_start_to_finish_when_both_are_known() -> None:
    finished = STARTED + timedelta(minutes=4, seconds=30)

    summary = summarise_investigation(_run(finished=finished), turns=())

    assert summary.duration_seconds == pytest.approx(270.0)


def test_duration_is_omitted_not_zero_while_the_run_has_not_finished() -> None:
    """The run genuinely has no end yet — that is 'unknown', not 'instant'."""
    summary = summarise_investigation(_run(finished=None), turns=(_turn(0),))

    assert summary.duration_seconds is None


def test_cost_sums_the_turns_that_actually_carry_a_priced_figure() -> None:
    summary = summarise_investigation(_run(), turns=(_turn(0, cost=0.12), _turn(1, cost=0.08)))

    assert summary.cost_usd == pytest.approx(0.20)


def test_cost_is_omitted_not_zero_when_no_turn_carries_a_cost_figure() -> None:
    """No turn reported a price — this is 'unknown', not 'free'."""
    summary = summarise_investigation(_run(), turns=(_turn(0), _turn(1)))

    assert summary.cost_usd is None


def test_cost_is_omitted_not_zero_when_there_are_no_turns_at_all() -> None:
    summary = summarise_investigation(_run(), turns=())

    assert summary.cost_usd is None


def test_a_turn_priced_at_exactly_zero_is_a_real_zero_not_an_absence() -> None:
    """One priced call, genuinely free, is a known fact and is included."""
    summary = summarise_investigation(_run(), turns=(_turn(0, cost=0.0),))

    assert summary.cost_usd == 0.0


def test_a_mix_of_priced_and_unpriced_turns_sums_only_what_is_known() -> None:
    """Reads what exists rather than recalculating — the unpriced turn is silent, not zero."""
    summary = summarise_investigation(_run(), turns=(_turn(0, cost=1.5), _turn(1, cost=None)))

    assert summary.cost_usd == pytest.approx(1.5)


def test_the_three_numbers_are_independent_of_each_other() -> None:
    """A case where all three are simultaneously present, to prove none is faked to satisfy another."""
    finished = STARTED + timedelta(seconds=42)
    summary = summarise_investigation(
        _run(finished=finished), turns=(_turn(0, cost=0.05), _turn(1, cost=0.05))
    )

    assert summary == InvestigationSummary(
        step_count=2, duration_seconds=pytest.approx(42.0), cost_usd=pytest.approx(0.10)
    )
