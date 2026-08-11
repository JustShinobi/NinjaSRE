"""Outbound delivery: masked, bounded, and remembered whether or not it arrived.

A report that did not arrive is worse than one that never existed, because
somebody is waiting for it — and the only thing worse is one that did not arrive
and left no trace. So every attempt is a row, the failures carry their reason,
and the retry stops at a named bound rather than becoming the outage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.transit import (
    DELIVERY_DETAIL_FULL_REPORT,
    DELIVERY_DETAIL_SUMMARY_WITH_LINK,
    DELIVERY_EVENT_APPROVAL_PENDING,
    DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
    DELIVERY_EVENT_REMEDIATION_PROPOSED,
    DELIVERY_EVENT_SOURCE_DEGRADED,
    MAX_DELIVERY_SUMMARY_CHARS,
    MAX_OUTBOUND_ATTEMPTS,
    OUTBOUND_RETRY_BACKOFF_SECONDS,
)
from platform.config_service.schema import RootConfig
from platform.delivery.dispatch import (
    DeliveryDispatcher,
    OutboundMessage,
    Transport,
    resend,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    TenantScope,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
)

pytestmark = pytest.mark.unit

ORG = "acme"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
SENTINEL_ADDRESS = "203.0.113.77"


def config(
    *, detail: str = DELIVERY_DETAIL_FULL_REPORT, events: list[str] | None = None
) -> RootConfig:
    """Return a configuration with one Slack destination for ``events``."""
    return RootConfig.of(
        {
            "surfaces": {"channels": [{"platform": "slack", "channel": "#incidents"}]},
            "transit": {
                "destinations": [
                    {
                        "destination_id": "ops",
                        "channel": "slack",
                        "events": events or [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
                        "detail": detail,
                    }
                ]
            },
        }
    )


@pytest.fixture
async def gateway() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


def dispatcher(
    gateway: FakePersistence,
    *,
    settings: RootConfig | None = None,
    transport: Transport | None = None,
) -> DeliveryDispatcher:
    """Return a dispatcher over ``gateway`` with a fixed clock."""
    return DeliveryDispatcher(
        gateway=gateway,
        scope=TenantScope(org_id=ORG),
        settings=settings if settings is not None else config(),
        channels=("slack",),
        transport=transport,
        clock=lambda: AT,
    )


async def sent(gateway: FakePersistence) -> tuple[TransitDelivery, ...]:
    """Return every outbound row the ledger holds."""
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.transit.deliveries(TransitQuery(directions=(TransitDirection.OUTBOUND,)))


# --- Dispatch ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "event",
    [
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
        DELIVERY_EVENT_REMEDIATION_PROPOSED,
        DELIVERY_EVENT_APPROVAL_PENDING,
        DELIVERY_EVENT_SOURCE_DEGRADED,
    ],
)
async def test_every_event_in_the_closed_set_reaches_a_destination_that_wants_it(
    gateway: FakePersistence, event: str
) -> None:
    """Including the approval event 061 will publish: the enum ships with it."""
    carried: list[OutboundMessage] = []

    async def transport(message: OutboundMessage) -> None:
        carried.append(message)

    result = await dispatcher(
        gateway, settings=config(events=[event]), transport=transport
    ).dispatch(event, subject="something happened", body="the whole story")

    assert [message.event for message in carried] == [event]
    assert len(result.delivered) == 1


async def test_a_destination_not_subscribed_is_not_told(gateway: FakePersistence) -> None:
    carried: list[OutboundMessage] = []

    async def transport(message: OutboundMessage) -> None:
        carried.append(message)

    await dispatcher(
        gateway,
        settings=config(events=[DELIVERY_EVENT_SOURCE_DEGRADED]),
        transport=transport,
    ).dispatch(DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b")

    assert carried == []


async def test_every_attempt_is_a_ledger_row(gateway: FakePersistence) -> None:
    async def transport(message: OutboundMessage) -> None:
        return None

    await dispatcher(gateway, transport=transport).dispatch(
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b"
    )

    rows = await sent(gateway)
    assert len(rows) == 1
    assert rows[0].outcome is TransitOutcome.DELIVERED


async def test_a_failed_attempt_is_a_row_carrying_its_reason(
    gateway: FakePersistence,
) -> None:
    async def transport(message: OutboundMessage) -> None:
        raise ConnectionError("the channel refused the message")

    result = await dispatcher(gateway, transport=transport).dispatch(
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b"
    )

    assert len(result.failed) == 1
    rows = await sent(gateway)
    assert "refused the message" in rows[0].reason


async def test_a_deployment_with_no_transport_fails_visibly_rather_than_silently(
    gateway: FakePersistence,
) -> None:
    """The composition root supplies the transport, and a missing one is a fact."""
    result = await dispatcher(gateway).dispatch(
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b"
    )

    assert len(result.failed) == 1
    assert "no transport wired" in result.failed[0].reason


# --- What actually leaves ----------------------------------------------------------


async def test_the_body_passes_the_masking_policy_before_it_leaves(
    gateway: FakePersistence,
) -> None:
    """Article IV's seam: no destination receives what the policy holds back."""
    carried: list[OutboundMessage] = []

    async def transport(message: OutboundMessage) -> None:
        carried.append(message)

    await dispatcher(gateway, transport=transport).dispatch(
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
        subject="checkout is down",
        body=f"the host at {SENTINEL_ADDRESS} stopped answering",
    )

    assert SENTINEL_ADDRESS not in carried[0].body


async def test_the_safe_detail_level_sends_a_summary_rather_than_the_report(
    gateway: FakePersistence,
) -> None:
    carried: list[OutboundMessage] = []

    async def transport(message: OutboundMessage) -> None:
        carried.append(message)

    await dispatcher(
        gateway,
        settings=config(detail=DELIVERY_DETAIL_SUMMARY_WITH_LINK),
        transport=transport,
    ).dispatch(
        DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
        subject="s",
        body="word " * 1_000,
        link="https://console.test/runs/run-1",
    )

    assert len(carried[0].body) <= MAX_DELIVERY_SUMMARY_CHARS + 1
    assert carried[0].link == "https://console.test/runs/run-1"


async def test_the_full_report_level_sends_the_whole_thing(
    gateway: FakePersistence,
) -> None:
    carried: list[OutboundMessage] = []

    async def transport(message: OutboundMessage) -> None:
        carried.append(message)

    body = "word " * 1_000
    await dispatcher(
        gateway, settings=config(detail=DELIVERY_DETAIL_FULL_REPORT), transport=transport
    ).dispatch(DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body=body)

    assert carried[0].body == body


# --- Retry ------------------------------------------------------------------------


async def test_the_retry_schedule_is_the_declared_one(gateway: FakePersistence) -> None:
    engine = dispatcher(gateway)

    schedule = [engine.next_backoff(attempt) for attempt in range(1, MAX_OUTBOUND_ATTEMPTS + 1)]

    assert schedule == [*OUTBOUND_RETRY_BACKOFF_SECONDS, None]


async def test_retrying_past_the_bound_is_refused_rather_than_slowed(
    gateway: FakePersistence,
) -> None:
    """Then the delivery is left failed for a person to re-send, which is the point."""
    engine = dispatcher(gateway)

    assert engine.next_backoff(MAX_OUTBOUND_ATTEMPTS) is None
    assert engine.next_backoff(MAX_OUTBOUND_ATTEMPTS + 1) is None


async def test_a_retry_is_a_row_of_its_own_one_attempt_further_on(
    gateway: FakePersistence,
) -> None:
    async def transport(message: OutboundMessage) -> None:
        raise ConnectionError("still down")

    engine = dispatcher(gateway, transport=transport)
    first = (
        await engine.dispatch(DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b")
    ).failed[0]

    second = await engine.retry(
        first,
        OutboundMessage(
            destination_id="ops", channel="slack", event=first.event_type, subject="s", body="b"
        ),
    )

    assert second.attempt == 2
    assert len(await sent(gateway)) == 2


# --- The human act ------------------------------------------------------------------


async def test_a_re_send_is_audited_even_when_it_fails_again(
    gateway: FakePersistence,
) -> None:
    """Who asked for a report to be sent again is a fact about a person's action."""

    async def transport(message: OutboundMessage) -> None:
        raise ConnectionError("still down")

    engine = dispatcher(gateway, transport=transport)
    failed = (
        await engine.dispatch(DELIVERY_EVENT_INVESTIGATION_CONCLUDED, subject="s", body="b")
    ).failed[0]

    row = await resend(engine, failed, actor_id="ada")

    assert row.outcome is TransitOutcome.FAILED
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query(action="delivery.resend")
    assert [event.actor_id for event in events] == ["ada"]
