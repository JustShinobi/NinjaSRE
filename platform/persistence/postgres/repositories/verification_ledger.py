"""The record of what has been checked, in PostgreSQL, upserted rather than inserted.

``ON CONFLICT DO UPDATE`` on ``(org_id, kind, subject)``: the identity is what
was checked rather than a generated key, so checking the same integration a
second time lands on its own row. That is what makes "one answer per thing" a
statement about the table instead of about every caller.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from config.constants.first_run import MAX_VERIFICATION_PAGE_SIZE
from platform.persistence.ports.verification_ledger import (
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
    check_verification_limit,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    rows_affected,
)


class PostgresVerificationLedger(TenantBound):
    """One organisation's record of what has been checked, inside one transaction."""

    async def record(self, record: VerificationRecord) -> VerificationRecord:
        """Store ``record``, replacing any earlier answer about the same thing."""
        statement = insert(models.VerificationRow).values(
            org_id=self.org_id,
            kind=record.kind.value,
            subject=record.subject,
            outcome=record.outcome.value,
            checked_at=record.checked_at,
            detail=record.detail,
            checked_by=record.checked_by,
            team_node_id=record.team_node_id,
            model_id=record.model_id,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "kind", "subject"],
                set_={
                    "outcome": statement.excluded.outcome,
                    "checked_at": statement.excluded.checked_at,
                    "detail": statement.excluded.detail,
                    "checked_by": statement.excluded.checked_by,
                    "team_node_id": statement.excluded.team_node_id,
                    "model_id": statement.excluded.model_id,
                },
            )
        )
        return record

    async def latest(self, *, kind: VerificationSubject, subject: str) -> VerificationRecord | None:
        """Return what is known about one thing, or ``None`` if nobody has checked it."""
        row = await self.session.get(models.VerificationRow, (self.org_id, kind.value, subject))
        return None if row is None else _record(row)

    async def records(
        self,
        *,
        kind: VerificationSubject | None = None,
        limit: int = MAX_VERIFICATION_PAGE_SIZE,
    ) -> tuple[VerificationRecord, ...]:
        """Return the recorded checks, by kind then subject."""
        bound = check_verification_limit(limit)
        statement = select(models.VerificationRow).where(
            models.VerificationRow.org_id == self.org_id
        )
        if kind is not None:
            statement = statement.where(models.VerificationRow.kind == kind.value)
        statement = statement.order_by(
            models.VerificationRow.kind,
            models.VerificationRow.subject,
        ).limit(bound)
        found = await self.session.execute(statement)
        return tuple(_record(row) for row in found.scalars())

    async def forget(self, *, kind: VerificationSubject, subject: str) -> bool:
        """Delete what was recorded about one thing, and say whether there was any."""
        removed = await self.session.execute(
            delete(models.VerificationRow).where(
                models.VerificationRow.org_id == self.org_id,
                models.VerificationRow.kind == kind.value,
                models.VerificationRow.subject == subject,
            )
        )
        return rows_affected(removed) > 0


def _record(row: models.VerificationRow) -> VerificationRecord:
    """Return the stored row as the record callers hold."""
    return VerificationRecord(
        subject=row.subject,
        kind=VerificationSubject(row.kind),
        outcome=VerificationOutcome(row.outcome),
        checked_at=as_utc(row.checked_at) or row.checked_at,
        detail=row.detail,
        checked_by=row.checked_by,
        team_node_id=row.team_node_id,
        model_id=row.model_id,
    )


__all__ = ["PostgresVerificationLedger"]
