"""What a run listing says about the investigations that have stopped for a person.

A console listing twenty running investigations is read to answer one question:
which of these needs me. A run that is working and a run that has been stopped
for eleven minutes waiting on an approval look identical in a status column, and
the second one is the only one worth opening.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import TRIGGER_ALERT
from core.agent.interaction import (
    Attention,
    AttentionState,
    InteractionRegistry,
    attention_of,
    question,
)
from platform.persistence.ports import RunStatus, UnitOfWork
from platform.runs.events import TraceEventKind
from platform.runs.history import RunHistory, RunQuery, attention_from
from platform.runs.recorder import RunRecorder

pytestmark = pytest.mark.unit


def _recorder(uow: UnitOfWork, clock: Callable[[], datetime], *, prefix: str) -> RunRecorder:
    counter = iter(range(10_000))
    return RunRecorder(
        store=uow.run_traces, clock=clock, ids=lambda: f"{prefix}-{next(counter):04d}"
    )


async def _started(uow: UnitOfWork, clock: Callable[[], datetime], *, run_id: str) -> RunRecorder:
    writer = _recorder(uow, clock, prefix=run_id)
    await writer.start_run(
        trigger=TRIGGER_ALERT,
        principal_id=PRINCIPAL,
        team_node_id=TEAM,
        run_id=run_id,
    )
    return writer


def _waiting(at: datetime) -> Attention:
    registry = InteractionRegistry(run_id="run-1", clock=lambda: at)
    registry.raise_interaction(
        question(
            interaction_id="i1",
            run_id="run-1",
            text="was the traffic spike the marketing launch?",
            at=at,
        )
    )
    return attention_of(registry)


# --- reading the recorded state --------------------------------------------------


def test_a_payload_with_no_attention_means_nobody_is_waiting() -> None:
    assert not attention_from({}).needs_attention


def test_a_payload_nothing_recognises_is_read_as_needing_nobody() -> None:
    """The safe direction to be wrong in: the run still appears in an unfiltered
    listing."""
    assert not attention_from({"attention": "waiting_on_a_haircut"}).needs_attention


def test_a_recorded_state_comes_back_whole() -> None:
    read = attention_from(
        _waiting(datetime.fromisoformat("2026-03-01T12:00:00+00:00")).to_metadata()
    )

    assert read.state is AttentionState.WAITING_ON_QUESTION
    assert read.waiting_since == datetime.fromisoformat("2026-03-01T12:00:00+00:00")


# --- writing it, and reading it back through the history --------------------------


async def test_a_run_reports_what_it_is_waiting_on(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = await _started(uow, clock, run_id="run-blocked")
    await writer.record_attention("run-blocked", _waiting(clock()))

    attention = await RunHistory(store=uow.run_traces).attention_of("run-blocked")

    assert attention.state is AttentionState.WAITING_ON_QUESTION
    assert "marketing launch" in attention.summary


async def test_the_latest_recorded_state_wins(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    """A run blocks and unblocks several times, and only the log holds the
    states in between."""
    writer = await _started(uow, clock, run_id="run-1")
    await writer.record_attention("run-1", _waiting(clock()))
    await writer.record_attention("run-1", Attention())

    attention = await RunHistory(store=uow.run_traces).attention_of("run-1")

    assert not attention.needs_attention


async def test_a_run_nobody_ever_waited_on_needs_nobody(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    await _started(uow, clock, run_id="run-quiet")

    assert not (await RunHistory(store=uow.run_traces).attention_of("run-quiet")).needs_attention


async def test_a_finished_run_needs_nobody_whatever_it_last_recorded(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    """A run that concluded with a question open has that question superseded,
    and a listing that still showed it blocked would send somebody to answer a
    run that is over."""
    writer = await _started(uow, clock, run_id="run-done")
    await writer.record_attention("run-done", _waiting(clock()))
    await writer.complete_run("run-done", status=RunStatus.COMPLETED, summary="Pool exhaustion.")

    assert not (await RunHistory(store=uow.run_traces).attention_of("run-done")).needs_attention


async def test_a_run_that_does_not_exist_needs_nobody(uow: UnitOfWork) -> None:
    assert not (await RunHistory(store=uow.run_traces).attention_of("nope")).needs_attention


# --- the listing the console reads -------------------------------------------------


async def test_the_listing_returns_only_the_runs_that_have_stopped_for_somebody(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    blocked = await _started(uow, clock, run_id="run-blocked")
    await _started(uow, clock, run_id="run-working")
    await blocked.record_attention("run-blocked", _waiting(clock()))

    waiting = await RunHistory(store=uow.run_traces).awaiting_a_human()

    assert [run.run_id for run, _ in waiting] == ["run-blocked"]
    assert waiting[0][1].state is AttentionState.WAITING_ON_QUESTION


async def test_the_longest_ignored_run_comes_first(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    """A queue sorted by how long it has been ignored is what stops the question
    nobody noticed from staying unanswered."""
    older_at = clock()
    first = await _started(uow, clock, run_id="run-older")
    second = await _started(uow, clock, run_id="run-newer")
    await first.record_attention("run-older", _waiting(older_at))
    await second.record_attention("run-newer", _waiting(clock()))

    waiting = await RunHistory(store=uow.run_traces).awaiting_a_human()

    assert [run.run_id for run, _ in waiting] == ["run-older", "run-newer"]


async def test_the_listing_honours_the_filters_every_other_listing_does(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = await _started(uow, clock, run_id="run-blocked")
    await writer.record_attention("run-blocked", _waiting(clock()))

    elsewhere = await RunHistory(store=uow.run_traces).awaiting_a_human(
        RunQuery(team_node_id="team-search")
    )

    assert elsewhere == ()


async def test_the_attention_event_is_in_the_runs_own_log(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    """It is part of the trace rather than beside it, so a replay of the
    incident shows when the agent stopped and why."""
    writer = await _started(uow, clock, run_id="run-1")
    await writer.record_attention("run-1", _waiting(clock()))

    events = await uow.run_traces.events_for_run("run-1")

    assert TraceEventKind.ATTENTION_CHANGED.value in {event.kind for event in events}
