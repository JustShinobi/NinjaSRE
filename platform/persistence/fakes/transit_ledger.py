"""In-memory transit ledger, keyed the way a real one is.

Deliveries are keyed by the caller's delivery id so a handler that retried its
own ledger write records one crossing rather than two, and samples are keyed by
source so there is exactly one per source without anybody having to delete the
previous one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.transit_ledger import (
    PayloadSample,
    SourceActivity,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
    check_transit_limit,
    matches,
)


@dataclass(slots=True)
class FakeTransitLedger:
    """One organisation's transit record."""

    org_id: str
    state: TenantState

    async def record(self, delivery: TransitDelivery) -> TransitDelivery:
        """Store ``delivery`` and return it, replacing any row with the same id."""
        self.state.transit_deliveries[delivery.delivery_id] = delivery
        return delivery

    async def deliveries(self, query: TransitQuery) -> tuple[TransitDelivery, ...]:
        """Return the rows matching ``query``, most recent first."""
        limit = check_transit_limit(query.limit)
        found = [row for row in self.state.transit_deliveries.values() if matches(row, query)]
        found.sort(key=lambda row: (row.occurred_at, row.delivery_id), reverse=True)
        return tuple(found[:limit])

    async def delivery(self, delivery_id: str) -> TransitDelivery | None:
        """Return one row by id, or ``None``."""
        return self.state.transit_deliveries.get(delivery_id)

    async def store_sample(self, sample: PayloadSample) -> PayloadSample:
        """Store ``sample`` as this source's only sample, replacing the last one."""
        self.state.transit_samples[sample.source] = sample
        return sample

    async def sample(self, source: str) -> PayloadSample | None:
        """Return the last masked payload this source sent, or ``None``."""
        return self.state.transit_samples.get(source)

    async def activity(
        self,
        *,
        direction: TransitDirection,
        since: datetime,
    ) -> tuple[SourceActivity, ...]:
        """Return per-source counts inside the window and each source's last delivery."""
        counts: dict[str, Counter[TransitOutcome]] = {}
        newest: dict[str, TransitDelivery] = {}
        for row in self.state.transit_deliveries.values():
            if row.direction is not direction:
                continue
            held = newest.get(row.source)
            if held is None or (row.occurred_at, row.delivery_id) > (
                held.occurred_at,
                held.delivery_id,
            ):
                newest[row.source] = row
            if row.occurred_at >= since:
                counts.setdefault(row.source, Counter())[row.outcome] += 1

        return tuple(
            SourceActivity(
                source=source,
                direction=direction,
                last_delivery=newest[source],
                counts=dict(counts.get(source, Counter())),
            )
            for source in sorted(newest)
        )

    async def prune(self, *, before: datetime) -> int:
        """Delete delivery rows recorded before ``before`` and return how many went."""
        expired = [
            key for key, row in self.state.transit_deliveries.items() if row.occurred_at < before
        ]
        for key in expired:
            del self.state.transit_deliveries[key]
        return len(expired)


def purge_transit(tenant: TenantState, cutoff: datetime) -> int:
    """Delete one tenant's expired delivery rows, and return the count.

    Beside the fake rather than inside the sweeper for the reason
    ``purge_estate_history`` is: the sweeper knows which classes exist and this
    module knows which dictionaries one of them lives in, and putting both in
    one place is how the sweeper ends up holding every port's storage layout.
    """
    expired = [key for key, row in tenant.transit_deliveries.items() if row.occurred_at < cutoff]
    for key in expired:
        del tenant.transit_deliveries[key]
    return len(expired)


__all__ = ["FakeTransitLedger", "purge_transit"]
