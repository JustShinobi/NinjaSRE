"""Resumable session state over PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from platform.persistence.ports.session_store import SessionRecord
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    check_limit,
    utc_now,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _to_record(row: models.Session) -> SessionRecord:
    return SessionRecord(
        session_id=row.session_id,
        status=row.status,
        payload=dict(row.payload),
        run_id=row.run_id,
        updated_at=as_utc(row.updated_at),
        expires_at=as_utc(row.expires_at),
    )


@dataclass(slots=True)
class PostgresSessionStore(TenantBound):
    """Session records for one organisation."""

    async def save(self, record: SessionRecord) -> SessionRecord:
        """Store ``record``, replacing any earlier state under the same id."""
        payload = check_payload(record.payload, kind="session")
        row = await self.session.get(models.Session, (self.org_id, record.session_id))
        if row is None:
            row = models.Session(org_id=self.org_id, session_id=record.session_id)
            self.session.add(row)

        # Last write wins, which is correct here and nowhere else in this
        # package: a session is one run's own state, so there is no second
        # writer to lose a race against.
        row.status = record.status
        row.payload = payload
        row.run_id = record.run_id
        row.updated_at = record.updated_at or utc_now()
        row.expires_at = record.expires_at

        await self.session.flush()
        return _to_record(row)

    async def load(self, session_id: str) -> SessionRecord | None:
        """Return the stored session with ``session_id``, or ``None``."""
        row = await self.session.get(models.Session, (self.org_id, session_id))
        return _to_record(row) if row is not None else None

    async def delete(self, session_id: str) -> bool:
        """Delete ``session_id`` and return whether it existed."""
        row = await self.session.get(models.Session, (self.org_id, session_id))
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def list_resumable(
        self,
        *,
        statuses: tuple[str, ...] = (),
        limit: int = 50,
    ) -> tuple[SessionRecord, ...]:
        """Return sessions in any of ``statuses``, least recently updated first."""
        check_limit(limit)
        statement = (
            select(models.Session)
            .where(models.Session.org_id == self.org_id)
            # Oldest first: the caller is looking for work that has been
            # waiting, and the one that has waited longest is the one to resume.
            .order_by(models.Session.updated_at.asc(), models.Session.session_id.asc())
            .limit(limit)
        )
        if statuses:
            statement = statement.where(models.Session.status.in_(statuses))

        rows = await self.session.scalars(statement)
        return tuple(_to_record(row) for row in rows)


__all__ = ["PostgresSessionStore"]
