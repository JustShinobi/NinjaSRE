"""Contract: the transit record, and the five things a backend must never get wrong.

Recording the same crossing twice is one row; a source keeps exactly one masked
sample and it is the last one; a source that has been silent for a month still
answers "when did you last hear from me"; the page bound raises rather than
clamps; and one tenant's transit is invisible from another.

The second and third are the load-bearing ones. A ledger that kept every sample
would be a store of payloads nobody asked for, and a ledger whose "last
delivery" only reached inside the counting window would answer the same thing —
nothing — for a source that stopped in March and a source configured this
morning, which is the one distinction this whole port exists to make.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import at

from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import (
    PayloadSample,
    PersistenceGateway,
    TenantScope,
    TransitDelivery,
    TransitDirection,
    TransitLedger,
    TransitOutcome,
    TransitQuery,
)

pytestmark = pytest.mark.contract


def crossing(
    *,
    delivery_id: str = "alertmanager-1",
    direction: TransitDirection = TransitDirection.INGRESS,
    source: str = "alertmanager",
    minutes: float = 0.0,
    outcome: TransitOutcome = TransitOutcome.ACCEPTED,
    reason: str = "",
    matched_rule: str = "",
    attempt: int = 1,
) -> TransitDelivery:
    """Return one crossing of the boundary, at a fixed instant."""
    return TransitDelivery(
        delivery_id=delivery_id,
        direction=direction,
        source=source,
        occurred_at=at(minutes),
        outcome=outcome,
        reason=reason,
        matched_rule=matched_rule,
        team_node_id="payments",
        attempt=attempt,
    )


# --- Recording -------------------------------------------------------------------


async def test_a_crossing_recorded_twice_is_one_row(gateway: PersistenceGateway) -> None:
    """A handler that retried its own ledger write recorded one arrival."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        ledger: TransitLedger = uow.transit
        await ledger.record(crossing())
        await ledger.record(crossing(outcome=TransitOutcome.DUPLICATE))

        rows = await ledger.deliveries(TransitQuery())

    assert len(rows) == 1
    assert rows[0].outcome is TransitOutcome.DUPLICATE


async def test_every_outcome_survives_a_round_trip(gateway: PersistenceGateway) -> None:
    """Including the refusals — a rejection that leaves no trace is the silent failure."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        for index, outcome in enumerate(TransitOutcome):
            await uow.transit.record(
                crossing(
                    delivery_id=f"row-{index}",
                    minutes=index,
                    outcome=outcome,
                    reason="unverified" if outcome is not TransitOutcome.ACCEPTED else "",
                )
            )

        rows = await uow.transit.deliveries(TransitQuery())

    assert {row.outcome for row in rows} == set(TransitOutcome)


async def test_rows_come_back_newest_first(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="old", minutes=0))
        await uow.transit.record(crossing(delivery_id="new", minutes=10))

        rows = await uow.transit.deliveries(TransitQuery())

    assert [row.delivery_id for row in rows] == ["new", "old"]


async def test_a_rejection_keeps_its_reason(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(
            crossing(outcome=TransitOutcome.REJECTED, reason="payload is not valid JSON")
        )
        rows = await uow.transit.deliveries(TransitQuery(outcomes=(TransitOutcome.REJECTED,)))

    assert rows[0].reason == "payload is not valid JSON"


async def test_a_discard_with_no_reason_cannot_be_constructed() -> None:
    """Not a storage rule — a rule about the record, so no backend can miss it."""
    with pytest.raises(ValueError, match="discarded with no reason"):
        crossing(outcome=TransitOutcome.DISCARDED)


async def test_one_row_is_reachable_by_its_own_id(gateway: PersistenceGateway) -> None:
    """The simulate endpoint's other input: an operator picks a delivery they can see."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="pick-me"))

        found = await uow.transit.delivery("pick-me")
        missing = await uow.transit.delivery("never-happened")

    assert found is not None
    assert found.delivery_id == "pick-me"
    assert missing is None


# --- Filtering and bounds ---------------------------------------------------------


async def test_the_two_directions_are_separable(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="in"))
        await uow.transit.record(
            crossing(
                delivery_id="out",
                direction=TransitDirection.OUTBOUND,
                source="chat:incidents",
                outcome=TransitOutcome.DELIVERED,
            )
        )

        outbound = await uow.transit.deliveries(
            TransitQuery(directions=(TransitDirection.OUTBOUND,))
        )

    assert [row.delivery_id for row in outbound] == ["out"]


async def test_a_page_beyond_the_bound_raises_rather_than_clamps(
    gateway: PersistenceGateway,
) -> None:
    """A caller that asked for 5,000 and received 200 cannot tell that from there being 200."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        with pytest.raises(BoundExceeded, match="MAX_TRANSIT_PAGE_SIZE"):
            await uow.transit.deliveries(TransitQuery(limit=5_000))


# --- Samples ----------------------------------------------------------------------


async def test_a_source_keeps_exactly_one_sample_and_it_is_the_last(
    gateway: PersistenceGateway,
) -> None:
    """One per source is a property of the store, not of every caller remembering."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=at(0),
                body='{"status":"firing"}',
                masking_policy="standard",
            )
        )
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=at(5),
                body='{"status":"resolved"}',
                masking_policy="strict",
            )
        )

        held = await uow.transit.sample("alertmanager")

    assert held is not None
    assert held.body == '{"status":"resolved"}'
    assert held.masking_policy == "strict"


async def test_a_source_that_sent_nothing_has_no_sample(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        assert await uow.transit.sample("sentry") is None


async def test_samples_are_kept_apart_by_source(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        for source in ("alertmanager", "grafana"):
            await uow.transit.store_sample(
                PayloadSample(
                    source=source,
                    captured_at=at(0),
                    body=f'{{"from":"{source}"}}',
                    masking_policy="standard",
                )
            )

        alertmanager = await uow.transit.sample("alertmanager")
        grafana = await uow.transit.sample("grafana")

    assert alertmanager is not None
    assert grafana is not None
    assert alertmanager.body != grafana.body


# --- Activity ---------------------------------------------------------------------


async def test_the_last_delivery_reaches_outside_the_counting_window(
    gateway: PersistenceGateway,
) -> None:
    """The whole point of the port: silence is a reading, not an absence of one.

    A count over the last day is zero both for a source that stopped a month ago
    and for one nobody ever configured, and those are different facts.
    """
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="long-ago", minutes=0))

        activity = await uow.transit.activity(
            direction=TransitDirection.INGRESS,
            since=at(0) + timedelta(days=1),
        )

    assert len(activity) == 1
    assert activity[0].total == 0
    assert activity[0].last_delivery is not None
    assert activity[0].last_delivery.delivery_id == "long-ago"


async def test_counts_are_per_outcome_inside_the_window(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="a", minutes=1))
        await uow.transit.record(crossing(delivery_id="b", minutes=2))
        await uow.transit.record(
            crossing(
                delivery_id="c",
                minutes=3,
                outcome=TransitOutcome.REJECTED,
                reason="unverified",
            )
        )

        activity = await uow.transit.activity(direction=TransitDirection.INGRESS, since=at(0))

    counts = activity[0].counts
    assert counts[TransitOutcome.ACCEPTED] == 2
    assert counts[TransitOutcome.REJECTED] == 1
    assert activity[0].total == 3


async def test_activity_names_each_source_once(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="a", source="alertmanager", minutes=1))
        await uow.transit.record(crossing(delivery_id="b", source="alertmanager", minutes=2))
        await uow.transit.record(crossing(delivery_id="c", source="grafana", minutes=1))

        activity = await uow.transit.activity(direction=TransitDirection.INGRESS, since=at(0))

    assert [row.source for row in activity] == ["alertmanager", "grafana"]


async def test_activity_does_not_mix_the_directions(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="in", minutes=1))
        await uow.transit.record(
            crossing(
                delivery_id="out",
                direction=TransitDirection.OUTBOUND,
                source="chat:incidents",
                outcome=TransitOutcome.DELIVERED,
                minutes=1,
            )
        )

        ingress = await uow.transit.activity(direction=TransitDirection.INGRESS, since=at(0))

    assert [row.source for row in ingress] == ["alertmanager"]


# --- Retention and isolation ------------------------------------------------------


async def test_pruning_removes_rows_older_than_the_cutoff(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing(delivery_id="old", minutes=0))
        await uow.transit.record(crossing(delivery_id="new", minutes=60))

        removed = await uow.transit.prune(before=at(30))
        left = await uow.transit.deliveries(TransitQuery())

    assert removed == 1
    assert [row.delivery_id for row in left] == ["new"]


async def test_pruning_leaves_the_samples_alone(gateway: PersistenceGateway) -> None:
    """One per source, replaced rather than appended — the table is bounded already.

    Ageing samples out would delete "what does this source send" from exactly
    the sources that send rarely, which is the question a sample answers.
    """
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=at(0),
                body='{"status":"firing"}',
                masking_policy="standard",
            )
        )

        await uow.transit.prune(before=at(30))
        held = await uow.transit.sample("alertmanager")

    assert held is not None


async def test_one_tenant_cannot_see_another_s_transit(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.transit.record(crossing())
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=at(0),
                body='{"acme":true}',
                masking_policy="standard",
            )
        )

    async with gateway.begin(TenantScope(org_id="globex")) as other:
        assert await other.transit.deliveries(TransitQuery()) == ()
        assert await other.transit.sample("alertmanager") is None
        assert await other.transit.delivery("alertmanager-1") is None
