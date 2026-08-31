"""In-memory daily estate counts, kept the way a real one is.

The dictionary is keyed by ``snapshot_date`` and a write that finds a key
already there leaves it untouched, which is the whole of idempotence: a sweep
that ran twice in one day confirms the first sweep's counts rather than
replacing them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.estate_snapshot_store import (
    EstateDailySnapshot,
    check_overview_window,
)


@dataclass(slots=True)
class FakeEstateSnapshotStore:
    """One organisation's daily estate counts."""

    org_id: str
    state: TenantState

    async def record(self, snapshot: EstateDailySnapshot) -> EstateDailySnapshot:
        """Store `snapshot`, or return the one already recorded for its day."""
        existing = self.state.estate_daily_snapshots.get(snapshot.snapshot_date)
        if existing is not None:
            return existing
        self.state.estate_daily_snapshots[snapshot.snapshot_date] = snapshot
        return snapshot

    async def list_daily(
        self, *, since: date, until: date, limit: int = MAX_OVERVIEW_DAILY_BUCKETS
    ) -> tuple[EstateDailySnapshot, ...]:
        """Return the days between `since` and `until`, oldest first."""
        checked = check_overview_window(limit)
        found = [
            snapshot
            for day, snapshot in self.state.estate_daily_snapshots.items()
            if since <= day <= until
        ]
        found.sort(key=lambda snapshot: snapshot.snapshot_date)
        return tuple(found[:checked])


__all__ = ["FakeEstateSnapshotStore"]
