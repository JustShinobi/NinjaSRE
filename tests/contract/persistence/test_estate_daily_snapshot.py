"""Contract: the daily estate snapshot upserts by day and lists in order.

`EstateSnapshotStore`'s own docstring makes three claims `test_port_
conformance.py` never checks — it only proves the method exists, never that
it behaves this way: `record` is idempotent by `(org_id, snapshot_date)`
rather than last-write-wins, `list_daily` returns its series oldest first
regardless of write order, and it is bounded by `MAX_OVERVIEW_DAILY_BUCKETS`.
This is that behavioural proof, over the `gateway` fixture `conftest.py`
already parametrises across every available backend — the fake always, a
real PostgreSQL only where `--postgres` (or `NINJASRE_TEST_DATABASE_URL`)
made one reachable for this session, the same opt-in
`test_estate_daily_snapshot_migration.py` needs for its own, narrower
migration-only proof.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from conftest import PRIMARY_ORG, at

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import EstateDailySnapshot, PersistenceGateway, TenantScope

pytestmark = pytest.mark.contract


def _snapshot(day: date, total: int) -> EstateDailySnapshot:
    return EstateDailySnapshot(
        snapshot_date=day,
        total=total,
        captured_at=at(),
        counts_by_kind={"container": total},
        counts_by_health={"healthy": total},
    )


async def test_a_second_write_the_same_day_confirms_the_first_rather_than_overwriting_it(
    gateway: PersistenceGateway,
) -> None:
    day = date(2026, 8, 1)
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        first = await uow.estate_snapshots.record(_snapshot(day, 10))
        # A second sweep the same day, with different counts: the row must
        # not move, and `record` must hand back what actually landed rather
        # than the argument this call offered.
        second = await uow.estate_snapshots.record(_snapshot(day, 99))

    assert first.total == 10
    assert second.total == 10

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        rows = await uow.estate_snapshots.list_daily(since=day, until=day)
    assert [row.total for row in rows] == [10]


async def test_distinct_days_yield_distinct_rows(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 1), 10))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 2), 11))

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        rows = await uow.estate_snapshots.list_daily(since=date(2026, 8, 1), until=date(2026, 8, 2))
    assert [(row.snapshot_date, row.total) for row in rows] == [
        (date(2026, 8, 1), 10),
        (date(2026, 8, 2), 11),
    ]


async def test_list_daily_orders_oldest_first_regardless_of_write_order(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        # Written newest first, on purpose: the read's own order is the claim.
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 3), 3))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 1), 1))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 2), 2))

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        rows = await uow.estate_snapshots.list_daily(since=date(2026, 8, 1), until=date(2026, 8, 3))
    assert [row.snapshot_date for row in rows] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]


async def test_list_daily_excludes_days_outside_since_and_until(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await uow.estate_snapshots.record(_snapshot(date(2026, 7, 31), 7))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 1), 1))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 2), 2))
        await uow.estate_snapshots.record(_snapshot(date(2026, 8, 3), 3))

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        rows = await uow.estate_snapshots.list_daily(since=date(2026, 8, 1), until=date(2026, 8, 2))
    assert [row.snapshot_date for row in rows] == [date(2026, 8, 1), date(2026, 8, 2)]


async def test_list_daily_keeps_the_oldest_limit_rows_when_more_exist(
    gateway: PersistenceGateway,
) -> None:
    # More days in range than `limit` -- both implementations sort ascending
    # and slice/LIMIT after that, so the days kept are the oldest, not the
    # newest. A caller wanting the trailing window narrows `since`/`until`
    # itself (`gateway/http/routes/overview.py::_window`); this is the port's
    # own literal behaviour, not the overview's.
    start = date(2026, 1, 1)
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        for offset in range(5):
            await uow.estate_snapshots.record(_snapshot(start + timedelta(days=offset), offset))

    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        rows = await uow.estate_snapshots.list_daily(
            since=start, until=start + timedelta(days=4), limit=3
        )
    assert [row.snapshot_date for row in rows] == [
        start,
        start + timedelta(days=1),
        start + timedelta(days=2),
    ]


async def test_list_daily_refuses_a_limit_past_the_declared_maximum(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        with pytest.raises(BoundExceeded):
            await uow.estate_snapshots.list_daily(
                since=date(2026, 1, 1),
                until=date(2026, 1, 1),
                limit=MAX_OVERVIEW_DAILY_BUCKETS + 1,
            )
