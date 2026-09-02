"""Watching a live run, losing the connection, and coming back."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import MAX_STREAM_BUFFER_EVENTS, TRIGGER_ALERT
from platform.persistence.ports import UnitOfWork
from platform.runs.cursor import Cursor, CursorError
from platform.runs.events import RunEvent, TraceEventKind
from platform.runs.recorder import RecordedTurn, RunRecorder
from platform.runs.stream import (
    RunEventBroker,
    RunEventPublisher,
    RunStream,
    SubscriberTooSlow,
    Subscription,
)

RUN = "run-live"
ORG = "org-live"


def writer(uow: UnitOfWork, clock: Callable[[], datetime], broker: RunEventBroker) -> RunRecorder:
    """Return a recorder publishing this organisation's runs to ``broker``."""
    counter = iter(range(10_000))
    return RunRecorder(
        store=uow.run_traces,
        clock=clock,
        ids=lambda: f"id-{next(counter):04d}",
        events=RunEventPublisher(broker=broker, org_id=ORG),
    )


async def collected(subscription: Subscription) -> list[RunEvent]:
    """Return everything currently buffered for ``subscription``."""
    return [event async for event in subscription.drain()]


# -- the cursor ----------------------------------------------------------------


def test_a_cursor_round_trips_through_its_wire_form() -> None:
    cursor = Cursor(run_id="run-1", position=17)

    assert Cursor.parse(str(cursor)) == cursor


def test_a_fresh_cursor_reads_from_the_beginning() -> None:
    # ``None`` rather than -1: "everything after nothing" and "everything" are
    # the same request, and the store's signature spells the second with None.
    assert Cursor.start_of("run-1").after is None
    assert Cursor(run_id="run-1", position=0).after == 0


def test_a_mangled_cursor_raises_rather_than_restarting_the_stream() -> None:
    # Defaulting to the beginning would resend the whole run and look like it
    # was working.
    with pytest.raises(CursorError):
        Cursor.parse("not-a-cursor")
    with pytest.raises(CursorError):
        Cursor.parse("run-1:banana")


def test_a_cursor_never_moves_backwards() -> None:
    cursor = Cursor(run_id="run-1", position=9)

    assert cursor.advanced_to(4) == cursor
    assert cursor.advanced_to(11).position == 11


# -- live delivery -------------------------------------------------------------


async def test_a_subscriber_receives_events_as_they_happen(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    broker = RunEventBroker()
    subscription = broker.attach(RUN)
    recorder = writer(uow, clock, broker)

    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )
    await recorder.record_turn(RecordedTurn(run_id=RUN, index=0, model="m"))

    assert [event.kind for event in await collected(subscription)] == [
        TraceEventKind.RUN_STARTED,
        TraceEventKind.TURN_COMPLETED,
    ]


async def test_several_clients_observe_one_run(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    broker = RunEventBroker()
    first = broker.attach(RUN)
    second = broker.attach(RUN)
    recorder = writer(uow, clock, broker)

    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )

    assert broker.subscribers(RUN) == 2
    assert len(await collected(first)) == 1
    assert len(await collected(second)) == 1


async def test_detaching_stops_delivery(uow: UnitOfWork, clock: Callable[[], datetime]) -> None:
    broker = RunEventBroker()
    subscription = broker.attach(RUN)
    recorder = writer(uow, clock, broker)

    broker.detach(subscription)
    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )

    assert broker.subscribers(RUN) == 0
    assert await collected(subscription) == []


# -- reconnection --------------------------------------------------------------


async def test_a_client_that_reconnects_receives_every_missed_event_once(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    broker = RunEventBroker()
    recorder = writer(uow, clock, broker)
    stream = RunStream(store=uow.run_traces, broker=broker)

    watching = broker.attach(RUN)
    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )
    seen = await collected(watching)
    broker.detach(watching)

    # Disconnected. The run carries on and the log keeps everything.
    for index in range(3):
        await recorder.record_turn(RecordedTurn(run_id=RUN, index=index, model="m"))

    missed = await stream.replay_from(watching.cursor)

    assert [event.sequence for event in seen] == [0]
    assert [event.sequence for event in missed] == [1, 2, 3]
    # Exactly once: nothing the client already had comes back.
    assert not {event.sequence for event in seen} & {event.sequence for event in missed}


async def test_following_catches_up_from_the_log_before_going_live(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    broker = RunEventBroker()
    recorder = writer(uow, clock, broker)
    stream = RunStream(store=uow.run_traces, broker=broker)

    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )
    await recorder.record_turn(RecordedTurn(run_id=RUN, index=0, model="m"))

    events = stream.follow(Cursor.start_of(RUN))
    caught_up = [await anext(events), await anext(events)]
    await events.aclose()

    assert [event.kind for event in caught_up] == [
        TraceEventKind.RUN_STARTED,
        TraceEventKind.TURN_COMPLETED,
    ]
    assert broker.subscribers(RUN) == 0


async def test_an_event_recorded_during_catch_up_is_not_lost(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The subscription is registered before the log is read, so the window
    # between the two delivers rather than dropping.
    broker = RunEventBroker()
    recorder = writer(uow, clock, broker)
    stream = RunStream(store=uow.run_traces, broker=broker)

    await recorder.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )
    events = stream.follow(Cursor.start_of(RUN))
    first = await anext(events)

    await recorder.record_turn(RecordedTurn(run_id=RUN, index=0, model="m"))
    second = await anext(events)
    await events.aclose()

    assert first.kind is TraceEventKind.RUN_STARTED
    assert second.kind is TraceEventKind.TURN_COMPLETED
    assert second.sequence == first.sequence + 1


# -- backpressure --------------------------------------------------------------


async def test_a_slow_subscriber_is_dropped_rather_than_buffered_without_bound() -> None:
    # A client that falls behind holds its cursor and reads the backlog from the
    # log; an unbounded queue is a memory leak with a client attached.
    subscription = Subscription(run_id=RUN, cursor=Cursor.start_of(RUN))

    for sequence in range(MAX_STREAM_BUFFER_EVENTS + 5):
        subscription.offer(
            RunEvent(run_id=RUN, kind=TraceEventKind.TURN_COMPLETED, sequence=sequence)
        )

    assert subscription.overflowed
    with pytest.raises(SubscriberTooSlow):
        await collected(subscription)


async def test_publishing_does_not_wait_for_a_slow_reader(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    broker = RunEventBroker()
    slow = broker.attach(RUN)
    for sequence in range(MAX_STREAM_BUFFER_EVENTS + 1):
        slow.offer(RunEvent(run_id=RUN, kind=TraceEventKind.TURN_COMPLETED, sequence=sequence))

    healthy = broker.attach(RUN)
    await writer(uow, clock, broker).start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )

    assert len(await collected(healthy)) == 1


# -- across replicas -----------------------------------------------------------


async def test_a_bridge_carries_an_event_to_another_replicas_subscribers(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The recording replica is not necessarily the one a client is attached to.
    class Bridge:
        """A bridge joining two brokers in one process, as a network one would."""

        def __init__(self) -> None:
            self.organisations: list[str] = []
            self.listeners: list[Callable[[RunEvent], None]] = []

        async def publish(self, event: RunEvent, *, org_id: str) -> None:
            self.organisations.append(org_id)
            for listener in self.listeners:
                listener(event)

        def subscribe(self, deliver: Callable[[RunEvent], None]) -> None:
            self.listeners.append(deliver)

    bridge = Bridge()
    recording = RunEventBroker(bridge=bridge)
    serving = RunEventBroker(bridge=bridge)
    watching = serving.attach(RUN)

    await writer(uow, clock, recording).start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )

    assert [event.kind for event in await collected(watching)] == [TraceEventKind.RUN_STARTED]
    # The tenant crosses with the event. A replica that received one without it
    # could only forward it onward as everybody's.
    assert bridge.organisations == [ORG]


async def test_a_bridged_event_is_not_sent_back_across_the_bridge(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    class CountingBridge:
        """Counts what crosses it, so a loop shows up as a number."""

        def __init__(self) -> None:
            self.crossings = 0
            self.listeners: list[Callable[[RunEvent], None]] = []

        async def publish(self, event: RunEvent, *, org_id: str) -> None:
            self.crossings += 1
            for listener in self.listeners:
                listener(event)

        def subscribe(self, deliver: Callable[[RunEvent], None]) -> None:
            self.listeners.append(deliver)

    bridge = CountingBridge()
    recording = RunEventBroker(bridge=bridge)
    serving = RunEventBroker(bridge=bridge)
    serving.attach(RUN)

    await writer(uow, clock, recording).start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=RUN
    )

    assert bridge.crossings == 1
