"""The deployment channel's broker: fan-out, memory, and a slow reader's fate."""

from __future__ import annotations

import asyncio

import pytest

from config.constants.runs import DEPLOYMENT_STREAM_BUFFER_EVENTS
from platform.runs.deployment import (
    DeploymentEventBroker,
    DeploymentEventKind,
    DeploymentScope,
    DeploymentSubscriberTooSlow,
)

pytestmark = pytest.mark.asyncio


async def test_a_fresh_broker_gets_a_random_epoch_that_does_not_change() -> None:
    broker = DeploymentEventBroker()
    epoch = broker.epoch
    assert epoch != ""
    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )
    assert broker.epoch == epoch


async def test_two_brokers_get_different_epochs() -> None:
    first = DeploymentEventBroker()
    second = DeploymentEventBroker()
    assert first.epoch != second.epoch


async def test_sequence_is_strictly_increasing_and_shared_across_scopes() -> None:
    broker = DeploymentEventBroker()
    run_event = await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )
    incident_event = await broker.publish(
        scope=DeploymentScope.INCIDENT,
        kind=DeploymentEventKind.INCIDENT_OPENED,
        payload={"incident_id": "i1"},
    )
    assert run_event.sequence == 1
    assert incident_event.sequence == 2


async def test_publishing_delivers_to_every_attached_subscriber() -> None:
    broker = DeploymentEventBroker()
    subscription_a, backlog_a = broker.attach()
    subscription_b, backlog_b = broker.attach()
    assert backlog_a == ()
    assert backlog_b == ()

    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )

    delivered_a = [event async for event in subscription_a.drain()]
    delivered_b = [event async for event in subscription_b.drain()]
    assert [event.kind for event in delivered_a] == [DeploymentEventKind.RUN_STARTED]
    assert [event.kind for event in delivered_b] == [DeploymentEventKind.RUN_STARTED]


async def test_detaching_stops_delivery() -> None:
    broker = DeploymentEventBroker()
    subscription, _ = broker.attach()
    broker.detach(subscription)

    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )

    delivered = [event async for event in subscription.drain()]
    assert delivered == []
    assert broker.subscriber_count == 0


async def test_the_buffer_is_bounded_by_the_declared_constant() -> None:
    broker = DeploymentEventBroker()
    for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 25):
        await broker.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": f"r{index}"},
        )
    assert len(broker._buffer) == DEPLOYMENT_STREAM_BUFFER_EVENTS  # noqa: SLF001 — the invariant under test


async def test_a_reconnection_within_the_buffer_is_served_the_backlog_not_a_resync() -> None:
    broker = DeploymentEventBroker()
    published = []
    for index in range(5):
        published.append(
            await broker.publish(
                scope=DeploymentScope.RUN,
                kind=DeploymentEventKind.RUN_STARTED,
                payload={"run_id": f"r{index}"},
            )
        )

    from platform.runs.deployment import DeploymentCursor

    cursor = DeploymentCursor(epoch=broker.epoch, sequence=2)
    _subscription, backlog = broker.attach(cursor)
    assert [event.sequence for event in backlog] == [3, 4, 5]
    assert all(event.kind != DeploymentEventKind.RESYNC for event in backlog)


async def test_a_gap_past_the_buffer_is_answered_with_exactly_one_resync() -> None:
    broker = DeploymentEventBroker()
    for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 25):
        await broker.publish(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            payload={"run_id": f"r{index}"},
        )

    from platform.runs.deployment import DeploymentCursor

    stale = DeploymentCursor(epoch=broker.epoch, sequence=1)
    _subscription, backlog = broker.attach(stale)
    assert len(backlog) == 1
    assert backlog[0].kind is DeploymentEventKind.RESYNC
    assert backlog[0].scope is DeploymentScope.CONTROL
    assert backlog[0].payload == {}


async def test_a_cursor_from_another_epoch_is_answered_with_resync() -> None:
    broker = DeploymentEventBroker()
    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )

    from platform.runs.deployment import DeploymentCursor

    foreign = DeploymentCursor(epoch="a-previous-process", sequence=1)
    _subscription, backlog = broker.attach(foreign)
    assert [event.kind for event in backlog] == [DeploymentEventKind.RESYNC]


async def test_a_first_connection_with_no_cursor_gets_no_backlog_at_all() -> None:
    broker = DeploymentEventBroker()
    await broker.publish(
        scope=DeploymentScope.RUN, kind=DeploymentEventKind.RUN_STARTED, payload={"run_id": "r1"}
    )

    _subscription, backlog = broker.attach(None)
    assert backlog == ()


async def test_a_slow_subscriber_does_not_block_publish() -> None:
    broker = DeploymentEventBroker()
    subscription, _ = broker.attach()

    # Publish well past the bounded queue without ever draining — this must
    # return promptly rather than waiting on the subscriber.
    async def flood() -> None:
        for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 20):
            await broker.publish(
                scope=DeploymentScope.RUN,
                kind=DeploymentEventKind.RUN_STARTED,
                payload={"run_id": f"r{index}"},
            )

    await asyncio.wait_for(flood(), timeout=1.0)
    assert subscription.overflowed is True

    with pytest.raises(DeploymentSubscriberTooSlow):
        async for _event in subscription.drain():
            pass
