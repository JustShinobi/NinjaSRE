"""The deployment channel's broker: fan-out, memory, tenancy, and a slow reader's fate.

Every event a write path publishes names the organisation it belongs to, and
every subscriber names the organisation it is allowed to hear about. The tests
below use two of them throughout — one broker, two tenants — because a channel
that is scoped correctly and a channel that has only ever been asked about one
tenant look identical from inside a single-org test.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.runs import DEPLOYMENT_STREAM_BUFFER_EVENTS
from platform.runs.deployment import (
    DeploymentCursor,
    DeploymentEventBroker,
    DeploymentEventKind,
    DeploymentScope,
    DeploymentSubscriberTooSlow,
)

pytestmark = pytest.mark.asyncio

#: Two organisations one deployment serves at once — the shape
#: `platform/startup/demo/seeder.py` creates and `platform/identity/tokens.py`
#: resolves a token into, not a hypothetical.
_ACME = "acme"
_INITECH = "initech"


async def _publish_run_started(broker: DeploymentEventBroker, run_id: str, *, org_id: str) -> None:
    """Publish one run-scope event attributed to ``org_id``."""
    await broker.publish(
        scope=DeploymentScope.RUN,
        kind=DeploymentEventKind.RUN_STARTED,
        payload={"run_id": run_id},
        org_id=org_id,
    )


async def test_a_fresh_broker_gets_a_random_epoch_that_does_not_change() -> None:
    broker = DeploymentEventBroker()
    epoch = broker.epoch
    assert epoch != ""
    await _publish_run_started(broker, "r1", org_id=_ACME)
    assert broker.epoch == epoch


async def test_two_brokers_get_different_epochs() -> None:
    first = DeploymentEventBroker()
    second = DeploymentEventBroker()
    assert first.epoch != second.epoch


async def test_sequence_is_strictly_increasing_and_shared_across_scopes() -> None:
    broker = DeploymentEventBroker()
    run_event = await broker.publish(
        scope=DeploymentScope.RUN,
        kind=DeploymentEventKind.RUN_STARTED,
        payload={"run_id": "r1"},
        org_id=_ACME,
    )
    incident_event = await broker.publish(
        scope=DeploymentScope.INCIDENT,
        kind=DeploymentEventKind.INCIDENT_OPENED,
        payload={"incident_id": "i1"},
        org_id=_ACME,
    )
    assert run_event.sequence == 1
    assert incident_event.sequence == 2


async def test_publishing_delivers_to_every_attached_subscriber_in_the_same_organisation() -> None:
    broker = DeploymentEventBroker()
    subscription_a, backlog_a = broker.attach(org_id=_ACME)
    subscription_b, backlog_b = broker.attach(org_id=_ACME)
    assert backlog_a == ()
    assert backlog_b == ()

    await _publish_run_started(broker, "r1", org_id=_ACME)

    delivered_a = [event async for event in subscription_a.drain()]
    delivered_b = [event async for event in subscription_b.drain()]
    assert [event.kind for event in delivered_a] == [DeploymentEventKind.RUN_STARTED]
    assert [event.kind for event in delivered_b] == [DeploymentEventKind.RUN_STARTED]


async def test_detaching_stops_delivery() -> None:
    broker = DeploymentEventBroker()
    subscription, _ = broker.attach(org_id=_ACME)
    broker.detach(subscription)

    await _publish_run_started(broker, "r1", org_id=_ACME)

    delivered = [event async for event in subscription.drain()]
    assert delivered == []
    assert broker.subscriber_count == 0


# --- Tenancy ------------------------------------------------------------------


async def test_an_event_reaches_only_the_organisation_it_belongs_to() -> None:
    """One process-wide broker, two tenants: the ids one organisation's writes
    produce are not facts about the other's deployment, and a subscriber holding
    the permission `GET /v1/runs` needs holds it within its own tenant only."""
    broker = DeploymentEventBroker()
    acme, _ = broker.attach(org_id=_ACME)
    initech, _ = broker.attach(org_id=_INITECH)

    await broker.publish(
        scope=DeploymentScope.INCIDENT,
        kind=DeploymentEventKind.INCIDENT_OPENED,
        payload={"incident_id": "acme-only"},
        org_id=_ACME,
    )
    await broker.publish(
        scope=DeploymentScope.DECISION,
        kind=DeploymentEventKind.DECISION_PROPOSED,
        payload={"proposal_id": "initech-only"},
        org_id=_INITECH,
    )

    seen_by_acme = [dict(event.payload) async for event in acme.drain()]
    seen_by_initech = [dict(event.payload) async for event in initech.drain()]
    assert seen_by_acme == [{"incident_id": "acme-only"}]
    assert seen_by_initech == [{"proposal_id": "initech-only"}]


async def test_the_backlog_a_reconnection_replays_is_filtered_the_same_way() -> None:
    """The live path and the catch-up path are two ways to the same wire, and a
    filter on only one of them is a filter a client gets past by reconnecting."""
    broker = DeploymentEventBroker()
    await broker.publish(
        scope=DeploymentScope.INCIDENT,
        kind=DeploymentEventKind.INCIDENT_OPENED,
        payload={"incident_id": "acme-only"},
        org_id=_ACME,
    )
    await broker.publish(
        scope=DeploymentScope.DECISION,
        kind=DeploymentEventKind.DECISION_PROPOSED,
        payload={"proposal_id": "initech-only"},
        org_id=_INITECH,
    )

    cursor = DeploymentCursor(epoch=broker.epoch, sequence=0)
    _subscription, backlog = broker.attach(cursor, org_id=_INITECH)
    assert [dict(event.payload) for event in backlog] == [{"proposal_id": "initech-only"}]


async def test_an_event_no_publisher_could_attribute_still_reaches_everyone() -> None:
    """``org_id=None`` is not "unfiltered by default" — it is the honest answer
    for a publisher with no tenant to read.

    `DeploymentPublishingRunEventBroker` is the only one today: a `RunEvent`
    carries no organisation and that broker is built once per process, so a
    run-scope frame is published unattributed and still fans out to every
    subscriber, exactly as it did before this channel learned about tenants.
    Narrowing it needs the run's own scope to reach that call, which is a
    change to `platform/runs/events.py` and `gateway/http/asgi.py`.
    """
    broker = DeploymentEventBroker()
    acme, _ = broker.attach(org_id=_ACME)
    initech, _ = broker.attach(org_id=_INITECH)

    await _publish_run_started(broker, "r1", org_id=None)

    assert [event.kind async for event in acme.drain()] == [DeploymentEventKind.RUN_STARTED]
    assert [event.kind async for event in initech.drain()] == [DeploymentEventKind.RUN_STARTED]


# --- Memory, cursors, and resync ----------------------------------------------


async def test_the_buffer_is_bounded_by_the_declared_constant() -> None:
    broker = DeploymentEventBroker()
    for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 25):
        await _publish_run_started(broker, f"r{index}", org_id=_ACME)
    assert len(broker._buffer) == DEPLOYMENT_STREAM_BUFFER_EVENTS  # noqa: SLF001 — the invariant under test


async def test_a_reconnection_within_the_buffer_is_served_the_backlog_not_a_resync() -> None:
    broker = DeploymentEventBroker()
    for index in range(5):
        await _publish_run_started(broker, f"r{index}", org_id=_ACME)

    cursor = DeploymentCursor(epoch=broker.epoch, sequence=2)
    _subscription, backlog = broker.attach(cursor, org_id=_ACME)
    assert [event.sequence for event in backlog] == [3, 4, 5]
    assert all(event.kind != DeploymentEventKind.RESYNC for event in backlog)


async def test_a_gap_past_the_buffer_is_answered_with_exactly_one_resync() -> None:
    broker = DeploymentEventBroker()
    for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 25):
        await _publish_run_started(broker, f"r{index}", org_id=_ACME)

    stale = DeploymentCursor(epoch=broker.epoch, sequence=1)
    _subscription, backlog = broker.attach(stale, org_id=_ACME)
    assert len(backlog) == 1
    assert backlog[0].kind is DeploymentEventKind.RESYNC
    assert backlog[0].scope is DeploymentScope.CONTROL
    assert backlog[0].payload == {}


async def test_a_cursor_from_another_epoch_is_answered_with_resync() -> None:
    broker = DeploymentEventBroker()
    await _publish_run_started(broker, "r1", org_id=_ACME)

    foreign = DeploymentCursor(epoch="a-previous-process", sequence=1)
    _subscription, backlog = broker.attach(foreign, org_id=_ACME)
    assert [event.kind for event in backlog] == [DeploymentEventKind.RESYNC]


async def test_a_first_connection_with_no_cursor_gets_no_backlog_at_all() -> None:
    broker = DeploymentEventBroker()
    await _publish_run_started(broker, "r1", org_id=_ACME)

    _subscription, backlog = broker.attach(None, org_id=_ACME)
    assert backlog == ()


async def test_a_slow_subscriber_does_not_block_publish() -> None:
    broker = DeploymentEventBroker()
    subscription, _ = broker.attach(org_id=_ACME)

    # Publish well past the bounded queue without ever draining — this must
    # return promptly rather than waiting on the subscriber.
    async def flood() -> None:
        for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 20):
            await _publish_run_started(broker, f"r{index}", org_id=_ACME)

    await asyncio.wait_for(flood(), timeout=1.0)
    assert subscription.overflowed is True

    with pytest.raises(DeploymentSubscriberTooSlow):
        async for _event in subscription.drain():
            pass


async def test_another_tenants_flood_never_fills_this_subscribers_buffer() -> None:
    """Filtering at `offer` rather than at the wire is what makes this true: an
    event a subscriber may not see never occupies a slot in its queue, so one
    busy tenant cannot push another's client into `resync`."""
    broker = DeploymentEventBroker()
    quiet, _ = broker.attach(org_id=_ACME)

    for index in range(DEPLOYMENT_STREAM_BUFFER_EVENTS + 20):
        await _publish_run_started(broker, f"r{index}", org_id=_INITECH)

    assert quiet.overflowed is False
    assert [event async for event in quiet.drain()] == []
