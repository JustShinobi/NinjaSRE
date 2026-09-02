"""One day's estate, counted — the only history a live summary cannot answer.

`GET /v1/overview` draws a sparkline of "resources watched" over the last
`MAX_OVERVIEW_DAILY_BUCKETS` days, and nothing else in this deployment keeps
that series: `EstateRepository.summarise` answers only "right now", and asking
it what the estate looked like a week ago is asking a fact nobody wrote down.

**A snapshot is a fact about a day, not a fact about a moment.** The first
sweep of a day that reaches this store writes the row; every later sweep the
same day leaves it exactly as it is — `record` is idempotent by
`(org_id, snapshot_date)`, and deliberately not "last sweep of the day wins":
the count a dashboard shows for "Tuesday" should be the same number whether it
is read at nine in the morning or at midnight, and a sweep late in the day
must not quietly rewrite what an operator already saw earlier the same day.

**Retroactive is not a mode this store has.** There is no parameter that backs
a value into a date other than the one it is recorded for, because a series
invented for a day nobody swept would look exactly like a series that was
measured — and be indistinguishable from it on the sparkline that reads it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from config.constants.estate import MAX_OVERVIEW_DAILY_BUCKETS
from platform.persistence.errors import BoundExceeded


@dataclass(frozen=True, slots=True)
class EstateDailySnapshot:
    """One organisation's estate, counted on one day.

    `total` and the two breakdowns are `EstateRepository.summarise`'s own
    shape, carried rather than re-derived, so the sparkline and the overview's
    own current-value tile can never disagree about what "counted" meant on
    the day this was taken.
    """

    snapshot_date: date
    total: int
    captured_at: datetime
    counts_by_kind: Mapping[str, int] = field(default_factory=dict)
    counts_by_health: Mapping[str, int] = field(default_factory=dict)


def check_overview_window(limit: int) -> int:
    """Return `limit`, or raise if it exceeds the overview's daily-bucket bound.

    Its own bound rather than the shared query one: the overview's sparkline
    is the only reader of `list_daily` and it never asks for more than
    `MAX_OVERVIEW_DAILY_BUCKETS` points.
    """
    if limit > MAX_OVERVIEW_DAILY_BUCKETS:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_OVERVIEW_DAILY_BUCKETS,
            constant="MAX_OVERVIEW_DAILY_BUCKETS",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


@runtime_checkable
class EstateSnapshotStore(Protocol):
    """One organisation's daily estate counts, inside one transaction."""

    async def record(self, snapshot: EstateDailySnapshot) -> EstateDailySnapshot:
        """Store `snapshot`, or return the one already recorded for its day.

        Idempotent by `snapshot_date`: the first call for a day writes it, and
        every later call the same day returns what is already stored, its own
        argument discarded. That is what keeps a sweep every fifteen minutes
        from producing ninety-six candidate values for one point on a
        fourteen-day sparkline, and what makes the answer this returns always
        the one actually on the row — never a value the caller merely offered.
        """

    async def list_daily(
        self, *, since: date, until: date, limit: int = MAX_OVERVIEW_DAILY_BUCKETS
    ) -> tuple[EstateDailySnapshot, ...]:
        """Return the days between `since` and `until`, oldest first.

        Raises `BoundExceeded` above `MAX_OVERVIEW_DAILY_BUCKETS`.
        """


__all__ = [
    "EstateDailySnapshot",
    "EstateSnapshotStore",
    "check_overview_window",
]
