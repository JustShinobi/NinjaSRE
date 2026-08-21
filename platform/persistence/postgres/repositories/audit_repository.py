"""Append-only audit events over PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from platform.persistence.errors import DuplicateRecord
from platform.persistence.ports.audit_repository import ActorKind, AuditEvent, AuditOutcome
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    check_limit,
    translating,
)


def _to_event(row: models.AuditEvent) -> AuditEvent:
    return AuditEvent(
        event_id=row.event_id,
        occurred_at=as_utc(row.occurred_at) or row.occurred_at,
        actor_kind=ActorKind(row.actor_kind),
        actor_id=row.actor_id,
        action=row.action,
        resource_kind=row.resource_kind,
        resource_id=row.resource_id,
        outcome=AuditOutcome(row.outcome),
        detail=dict(row.detail),
    )


@dataclass(slots=True)
class PostgresAuditRepository(TenantBound):
    """Audit events for one organisation.

    Four methods, none of which mutates or removes. The absence mirrors the
    port rather than merely respecting it: a repository with a private delete
    is one a retention pass could grow a call to.
    """

    async def append(self, event: AuditEvent) -> AuditEvent:
        """Store ``event`` and return it."""
        if await self.session.get(models.AuditEvent, (self.org_id, event.event_id)) is not None:
            raise DuplicateRecord(kind="audit event", identifier=event.event_id)

        row = models.AuditEvent(
            org_id=self.org_id,
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            actor_kind=event.actor_kind.value,
            actor_id=event.actor_id,
            action=event.action,
            resource_kind=event.resource_kind,
            resource_id=event.resource_id,
            outcome=event.outcome.value,
            detail=dict(event.detail),
        )
        self.session.add(row)
        with translating(kind="audit event", identifier=event.event_id):
            await self.session.flush()
        return _to_event(row)

    async def get(self, event_id: str) -> AuditEvent | None:
        """Return the event with ``event_id``, or ``None``."""
        row = await self.session.get(models.AuditEvent, (self.org_id, event_id))
        return _to_event(row) if row is not None else None

    async def query(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_kind: str | None = None,
        resource_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> tuple[AuditEvent, ...]:
        """Return matching events, most recent first."""
        check_limit(limit)
        statement = (
            select(models.AuditEvent)
            .where(models.AuditEvent.org_id == self.org_id)
            .order_by(
                models.AuditEvent.occurred_at.desc(),
                models.AuditEvent.event_id.desc(),
            )
            .limit(limit)
        )
        for clause in _filters(
            actor_id=actor_id,
            action=action,
            resource_kind=resource_kind,
            resource_id=resource_id,
            since=since,
            until=until,
        ):
            statement = statement.where(clause)

        rows = await self.session.scalars(statement)
        return tuple(_to_event(row) for row in rows)

    async def count(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Return how many events fall in the window."""
        statement = (
            select(func.count())
            .select_from(models.AuditEvent)
            .where(models.AuditEvent.org_id == self.org_id)
        )
        for clause in _filters(since=since, until=until):
            statement = statement.where(clause)
        return int(await self.session.scalar(statement) or 0)


def _filters(
    *,
    actor_id: str | None = None,
    action: str | None = None,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ColumnElement[bool]]:
    """Return the clauses for the filters that were given.

    The window is half-open — inclusive of ``since``, exclusive of ``until`` —
    so consecutive windows tile without double-counting the instant they meet.
    """
    clauses: list[ColumnElement[bool]] = []
    if actor_id is not None:
        clauses.append(models.AuditEvent.actor_id == actor_id)
    if action is not None:
        clauses.append(models.AuditEvent.action == action)
    if resource_kind is not None:
        clauses.append(models.AuditEvent.resource_kind == resource_kind)
    if resource_id is not None:
        clauses.append(models.AuditEvent.resource_id == resource_id)
    if since is not None:
        clauses.append(models.AuditEvent.occurred_at >= since)
    if until is not None:
        clauses.append(models.AuditEvent.occurred_at < until)
    return clauses


__all__ = ["PostgresAuditRepository"]
