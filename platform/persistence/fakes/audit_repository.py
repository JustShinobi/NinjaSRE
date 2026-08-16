"""In-memory append-only audit events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from platform.persistence.errors import DuplicateRecord
from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.audit_repository import AuditEvent


@dataclass(slots=True)
class FakeAuditRepository:
    """Audit events for one organisation.

    There is no method here that mutates or removes an event, which mirrors the
    port rather than merely respecting it: a fake with a private delete would be
    a fake the retention suite could not prove anything against.
    """

    org_id: str
    state: TenantState

    async def append(self, event: AuditEvent) -> AuditEvent:
        """Store ``event`` and return it."""
        if event.event_id in self.state.audit_events:
            raise DuplicateRecord(kind="audit event", identifier=event.event_id)
        check_payload(event.detail, kind="audit event")
        self.state.audit_events[event.event_id] = event
        return event

    async def get(self, event_id: str) -> AuditEvent | None:
        """Return the event with ``event_id``, or ``None``."""
        return self.state.audit_events.get(event_id)

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
        matches = [
            event
            for event in self.state.audit_events.values()
            if (actor_id is None or event.actor_id == actor_id)
            and (action is None or event.action == action)
            and (resource_kind is None or event.resource_kind == resource_kind)
            and (resource_id is None or event.resource_id == resource_id)
            and _within(event.occurred_at, since, until)
        ]
        matches.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)
        return tuple(matches[:limit])

    async def count(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_kind: str | None = None,
        resource_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Return how many events match the same filters ``query`` would apply."""
        return sum(
            1
            for event in self.state.audit_events.values()
            if (actor_id is None or event.actor_id == actor_id)
            and (action is None or event.action == action)
            and (resource_kind is None or event.resource_kind == resource_kind)
            and (resource_id is None or event.resource_id == resource_id)
            and _within(event.occurred_at, since, until)
        )


def _within(moment: datetime, since: datetime | None, until: datetime | None) -> bool:
    """Return whether ``moment`` falls in a half-open window.

    Inclusive of ``since`` and exclusive of ``until``, so consecutive windows
    tile without double-counting the instant they meet.
    """
    if since is not None and moment < since:
        return False
    return not (until is not None and moment >= until)


__all__ = ["FakeAuditRepository"]
