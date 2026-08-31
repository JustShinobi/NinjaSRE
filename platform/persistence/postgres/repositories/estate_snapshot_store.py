"""The estate's daily counts in PostgreSQL, written once and never overwritten.

``ON CONFLICT DO NOTHING`` rather than ``DO UPDATE``: the first sweep of a day
to reach this store is the one whose counts stand for that day, and every
later sweep the same day is a confirmation, not a correction. Selecting the
row back after the insert attempt is what lets ``record`` return the value
actually stored rather than the one the caller merely offered — the two agree
on the day's first call and may legitimately differ on every call after it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from platform.persistence.ports.estate_snapshot_store import (
    EstateDailySnapshot,
    check_overview_window,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import TenantBound, as_utc


class PostgresEstateSnapshotStore(TenantBound):
    """One organisation's daily estate counts, inside one transaction."""

    async def record(self, snapshot: EstateDailySnapshot) -> EstateDailySnapshot:
        """Store `snapshot`, or return the one already recorded for its day."""
        statement = insert(models.EstateDailySnapshotRow).values(_row(self.org_id, snapshot))
        await self.session.execute(
            statement.on_conflict_do_nothing(index_elements=["org_id", "snapshot_date"])
        )
        stored = await self.session.execute(
            select(models.EstateDailySnapshotRow).where(
                models.EstateDailySnapshotRow.org_id == self.org_id,
                models.EstateDailySnapshotRow.snapshot_date == snapshot.snapshot_date,
            )
        )
        return _snapshot(stored.scalar_one())

    async def list_daily(
        self, *, since: date, until: date, limit: int = MAX_OVERVIEW_DAILY_BUCKETS
    ) -> tuple[EstateDailySnapshot, ...]:
        """Return the days between `since` and `until`, oldest first."""
        checked = check_overview_window(limit)
        statement = (
            select(models.EstateDailySnapshotRow)
            .where(
                models.EstateDailySnapshotRow.org_id == self.org_id,
                models.EstateDailySnapshotRow.snapshot_date >= since,
                models.EstateDailySnapshotRow.snapshot_date <= until,
            )
            .order_by(models.EstateDailySnapshotRow.snapshot_date)
            .limit(checked)
        )
        found = await self.session.execute(statement)
        return tuple(_snapshot(row) for row in found.scalars())


def _row(org_id: str, snapshot: EstateDailySnapshot) -> dict[str, Any]:
    """Return `snapshot` as the column values one row binds from."""
    return {
        "org_id": org_id,
        "snapshot_date": snapshot.snapshot_date,
        "total": snapshot.total,
        "counts_by_kind": dict(snapshot.counts_by_kind),
        "counts_by_health": dict(snapshot.counts_by_health),
        "captured_at": snapshot.captured_at,
    }


def _snapshot(row: models.EstateDailySnapshotRow) -> EstateDailySnapshot:
    """Return the stored row as the record callers hold."""
    return EstateDailySnapshot(
        snapshot_date=row.snapshot_date,
        total=row.total,
        captured_at=as_utc(row.captured_at) or row.captured_at,
        counts_by_kind=dict(row.counts_by_kind),
        counts_by_health=dict(row.counts_by_health),
    )


__all__ = ["PostgresEstateSnapshotStore"]
