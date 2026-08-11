"""The transit record in PostgreSQL, upserted rather than inserted.

Both writes are ``ON CONFLICT DO UPDATE``, and for the same reason the signal
store's is: the identity is derived by the caller, so a handler that retried its
own ledger write lands on its own row. For the sample the conflict target is
``(org_id, source)`` itself, which is what makes "one sample per source" a
statement about the table rather than about every writer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from platform.persistence.ports.transit_ledger import (
    PayloadSample,
    SourceActivity,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
    check_transit_limit,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    rows_affected,
)


class PostgresTransitLedger(TenantBound):
    """One organisation's transit record, inside one transaction."""

    async def record(self, delivery: TransitDelivery) -> TransitDelivery:
        """Store ``delivery`` and return it, replacing any row with the same id."""
        statement = insert(models.TransitDeliveryRow).values(_row(self.org_id, delivery))
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "delivery_id"],
                set_={
                    "direction": statement.excluded.direction,
                    "source": statement.excluded.source,
                    "occurred_at": statement.excluded.occurred_at,
                    "outcome": statement.excluded.outcome,
                    "reason": statement.excluded.reason,
                    "matched_rule": statement.excluded.matched_rule,
                    "team_node_id": statement.excluded.team_node_id,
                    "resource_id": statement.excluded.resource_id,
                    "run_id": statement.excluded.run_id,
                    "incident_id": statement.excluded.incident_id,
                    "event_type": statement.excluded.event_type,
                    "attempt": statement.excluded.attempt,
                    "detail": statement.excluded.detail,
                },
            )
        )
        return delivery

    async def deliveries(self, query: TransitQuery) -> tuple[TransitDelivery, ...]:
        """Return the rows matching ``query``, most recent first."""
        limit = check_transit_limit(query.limit)
        statement = select(models.TransitDeliveryRow).where(
            models.TransitDeliveryRow.org_id == self.org_id
        )
        if query.directions:
            statement = statement.where(
                models.TransitDeliveryRow.direction.in_([d.value for d in query.directions])
            )
        if query.sources:
            statement = statement.where(models.TransitDeliveryRow.source.in_(query.sources))
        if query.outcomes:
            statement = statement.where(
                models.TransitDeliveryRow.outcome.in_([o.value for o in query.outcomes])
            )
        if query.since is not None:
            statement = statement.where(models.TransitDeliveryRow.occurred_at >= query.since)
        if query.until is not None:
            statement = statement.where(models.TransitDeliveryRow.occurred_at <= query.until)

        statement = statement.order_by(
            models.TransitDeliveryRow.occurred_at.desc(),
            models.TransitDeliveryRow.delivery_id.desc(),
        ).limit(limit)
        found = await self.session.execute(statement)
        return tuple(_delivery(row) for row in found.scalars())

    async def delivery(self, delivery_id: str) -> TransitDelivery | None:
        """Return one row by id, or ``None``."""
        row = await self.session.get(models.TransitDeliveryRow, (self.org_id, delivery_id))
        return None if row is None else _delivery(row)

    async def store_sample(self, sample: PayloadSample) -> PayloadSample:
        """Store ``sample`` as this source's only sample, replacing the last one."""
        statement = insert(models.TransitSampleRow).values(
            org_id=self.org_id,
            source=sample.source,
            captured_at=sample.captured_at,
            body=sample.body,
            masking_policy=sample.masking_policy,
            delivery_id=sample.delivery_id,
            truncated=sample.truncated,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "source"],
                set_={
                    "captured_at": statement.excluded.captured_at,
                    "body": statement.excluded.body,
                    "masking_policy": statement.excluded.masking_policy,
                    "delivery_id": statement.excluded.delivery_id,
                    "truncated": statement.excluded.truncated,
                },
            )
        )
        return sample

    async def sample(self, source: str) -> PayloadSample | None:
        """Return the last masked payload this source sent, or ``None``."""
        row = await self.session.get(models.TransitSampleRow, (self.org_id, source))
        return None if row is None else _sample(row)

    async def activity(
        self,
        *,
        direction: TransitDirection,
        since: datetime,
    ) -> tuple[SourceActivity, ...]:
        """Return per-source counts inside the window and each source's last delivery.

        Two statements rather than one: the counts are grouped and windowed, the
        last delivery deliberately is not — a source that stopped in March has
        no rows in the window and its silence is the answer being asked for.
        """
        grouped = await self.session.execute(
            select(
                models.TransitDeliveryRow.source,
                models.TransitDeliveryRow.outcome,
                func.count(),
            )
            .where(
                models.TransitDeliveryRow.org_id == self.org_id,
                models.TransitDeliveryRow.direction == direction.value,
                models.TransitDeliveryRow.occurred_at >= since,
            )
            .group_by(models.TransitDeliveryRow.source, models.TransitDeliveryRow.outcome)
        )
        counts: dict[str, Counter[TransitOutcome]] = {}
        for source, outcome, total in grouped.all():
            counts.setdefault(source, Counter())[TransitOutcome(outcome)] += int(total)

        newest = await self.session.execute(
            select(models.TransitDeliveryRow)
            .where(
                models.TransitDeliveryRow.org_id == self.org_id,
                models.TransitDeliveryRow.direction == direction.value,
            )
            .distinct(models.TransitDeliveryRow.source)
            .order_by(
                models.TransitDeliveryRow.source,
                models.TransitDeliveryRow.occurred_at.desc(),
                models.TransitDeliveryRow.delivery_id.desc(),
            )
        )
        return tuple(
            SourceActivity(
                source=row.source,
                direction=direction,
                last_delivery=_delivery(row),
                counts=dict(counts.get(row.source, Counter())),
            )
            for row in sorted(newest.scalars(), key=lambda row: row.source)
        )

    async def prune(self, *, before: datetime) -> int:
        """Delete delivery rows recorded before ``before`` and return how many went."""
        removed = await self.session.execute(
            delete(models.TransitDeliveryRow).where(
                models.TransitDeliveryRow.org_id == self.org_id,
                models.TransitDeliveryRow.occurred_at < before,
            )
        )
        return rows_affected(removed)


def _row(org_id: str, delivery: TransitDelivery) -> dict[str, Any]:
    """Return ``delivery`` as the column values one row binds from."""
    return {
        "org_id": org_id,
        "delivery_id": delivery.delivery_id,
        "direction": delivery.direction.value,
        "source": delivery.source,
        "occurred_at": delivery.occurred_at,
        "outcome": delivery.outcome.value,
        "reason": delivery.reason,
        "matched_rule": delivery.matched_rule,
        "team_node_id": delivery.team_node_id,
        "resource_id": delivery.resource_id,
        "run_id": delivery.run_id,
        "incident_id": delivery.incident_id,
        "event_type": delivery.event_type,
        "attempt": delivery.attempt,
        "detail": dict(delivery.detail),
    }


def _delivery(row: models.TransitDeliveryRow) -> TransitDelivery:
    """Return the stored row as the record callers hold."""
    return TransitDelivery(
        delivery_id=row.delivery_id,
        direction=TransitDirection(row.direction),
        source=row.source,
        occurred_at=as_utc(row.occurred_at) or row.occurred_at,
        outcome=TransitOutcome(row.outcome),
        reason=row.reason,
        matched_rule=row.matched_rule,
        team_node_id=row.team_node_id,
        resource_id=row.resource_id,
        run_id=row.run_id,
        incident_id=row.incident_id,
        event_type=row.event_type,
        attempt=row.attempt,
        detail=dict(row.detail),
    )


def _sample(row: models.TransitSampleRow) -> PayloadSample:
    """Return the stored sample as the record callers hold."""
    return PayloadSample(
        source=row.source,
        captured_at=as_utc(row.captured_at) or row.captured_at,
        body=row.body,
        masking_policy=row.masking_policy,
        delivery_id=row.delivery_id,
        truncated=row.truncated,
    )


__all__ = ["PostgresTransitLedger"]
