"""The observation history in PostgreSQL, upserted rather than inserted.

Every write is an ``ON CONFLICT DO UPDATE`` on the derived key. That is not an
optimisation — it is the property the whole store rests on: a poller that
retried, a replica that raced, and a worker that restarted mid-append all write
the same row, so an average over a window is an average over observations rather
than over deliveries.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from platform.persistence.ports.signal_store import (
    Signal,
    SignalKind,
    SignalQuery,
    check_signal_limit,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    rows_affected,
)


class PostgresSignalStore(TenantBound):
    """One organisation's signals, inside one transaction."""

    async def append(self, signals: Sequence[Signal]) -> tuple[Signal, ...]:
        """Store ``signals`` and return them, replacing any with the same key.

        The batch is collapsed by key before it is sent, keeping the last of
        each — which is what "replacing any with the same key" means when the
        duplicates arrive together rather than in separate calls.

        Not an optimisation. ``ON CONFLICT DO UPDATE`` refuses a statement that
        would touch one row twice, so a batch carrying two samples with the same
        key fails outright rather than keeping either. That is easy to produce
        without meaning to: the key is derived from name, resource, and instant,
        so one poller reporting the same series twice in a tick — from two
        sources, say — collides while looking like two distinct observations.
        """
        if not signals:
            return ()

        # dict preserves insertion order, so re-inserting under an existing key
        # overwrites the value while keeping the original position: last wins,
        # and the order the caller sent stays the order that is written.
        deduplicated = {signal.signal_id: signal for signal in signals}
        statement = insert(models.SignalRow).values(
            [_row(self.org_id, signal) for signal in deduplicated.values()]
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "signal_id"],
                set_={
                    "value": statement.excluded.value,
                    "state": statement.excluded.state,
                    "source": statement.excluded.source,
                    "kind": statement.excluded.kind,
                    "interval_seconds": statement.excluded.interval_seconds,
                    "labels": statement.excluded.labels,
                },
            )
        )
        return tuple(signals)

    async def window(self, query: SignalQuery) -> tuple[Signal, ...]:
        """Return the samples matching ``query``, oldest first."""
        limit = check_signal_limit(query.limit)
        statement = select(models.SignalRow).where(models.SignalRow.org_id == self.org_id)
        if query.names:
            statement = statement.where(models.SignalRow.name.in_(query.names))
        if query.resource_ids:
            statement = statement.where(models.SignalRow.resource_id.in_(query.resource_ids))
        if query.sources:
            statement = statement.where(models.SignalRow.source.in_(query.sources))
        if query.since is not None:
            statement = statement.where(models.SignalRow.observed_at >= query.since)
        if query.until is not None:
            statement = statement.where(models.SignalRow.observed_at <= query.until)

        statement = statement.order_by(
            models.SignalRow.observed_at, models.SignalRow.signal_id
        ).limit(limit)
        found = await self.session.execute(statement)
        return tuple(_signal(row) for row in found.scalars())

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per ``(name, resource)``, however old it is.

        ``DISTINCT ON`` rather than a window function: the composite index is
        already ordered by ``(name, resource_id, observed_at)``, so the newest
        per group is a backwards walk over it rather than a sort of everything.
        """
        statement = (
            select(models.SignalRow)
            .where(models.SignalRow.org_id == self.org_id)
            .distinct(models.SignalRow.name, models.SignalRow.resource_id)
            .order_by(
                models.SignalRow.name,
                models.SignalRow.resource_id,
                models.SignalRow.observed_at.desc(),
            )
        )
        if names:
            statement = statement.where(models.SignalRow.name.in_(names))
        if resource_ids:
            statement = statement.where(models.SignalRow.resource_id.in_(resource_ids))

        found = await self.session.execute(statement)
        return tuple(
            sorted((_signal(row) for row in found.scalars()), key=lambda signal: signal.signal_id)
        )

    async def prune(self, *, before: datetime) -> int:
        """Delete samples observed before ``before`` and return how many went."""
        removed = await self.session.execute(
            delete(models.SignalRow).where(
                models.SignalRow.org_id == self.org_id,
                models.SignalRow.observed_at < before,
            )
        )
        return rows_affected(removed)


def _row(org_id: str, signal: Signal) -> dict[str, Any]:
    """Return ``signal`` as the column values one row binds from."""
    return {
        "org_id": org_id,
        "signal_id": signal.signal_id,
        "name": signal.name,
        "resource_id": signal.resource_id,
        "source": signal.source,
        "kind": signal.kind.value,
        "observed_at": signal.observed_at,
        "value": signal.value,
        "state": signal.state,
        "interval_seconds": signal.interval_seconds,
        "labels": dict(signal.labels),
    }


def _signal(row: models.SignalRow) -> Signal:
    """Return the stored row as the record callers hold."""
    return Signal(
        signal_id=row.signal_id,
        name=row.name,
        resource_id=row.resource_id,
        source=row.source,
        kind=SignalKind(row.kind),
        observed_at=as_utc(row.observed_at) or row.observed_at,
        value=row.value,
        state=row.state,
        interval_seconds=row.interval_seconds,
        labels=dict(row.labels),
    )


__all__ = ["PostgresSignalStore"]
