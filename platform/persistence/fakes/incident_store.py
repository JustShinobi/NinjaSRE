"""In-memory incidents and their timelines, with the same guarantees as the real one.

Two dictionaries and the lookups the contract names. The one that matters is
``open_for``: it walks the live incidents rather than the most recent, because a
recurrence after a resolution must open its own incident instead of reviving a
piece of last week's history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from config.constants.observation import MAX_INCIDENT_TIMELINE
from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentQuery,
    TimelineEntry,
    check_incident_limit,
    check_timeline_limit,
    matches,
)


@dataclass(slots=True)
class FakeIncidentStore:
    """One organisation's incidents."""

    org_id: str
    state: TenantState

    async def upsert(self, incident: Incident) -> Incident:
        """Store ``incident``, replacing any earlier record with the same id."""
        self.state.incidents[incident.incident_id] = incident
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        """Return the incident with ``incident_id``, or ``None``."""
        return self.state.incidents.get(incident_id)

    async def get_by_public_id(self, public_id: str) -> Incident | None:
        """Return the incident whose public address is ``public_id``, or ``None``."""
        for incident in self.state.incidents.values():
            if incident.public_id == public_id:
                return incident
        return None

    async def open_for(self, correlation_key: str) -> Incident | None:
        """Return the live incident for ``correlation_key``, or ``None``."""
        live = [
            incident
            for incident in self.state.incidents.values()
            if incident.correlation_key == correlation_key and not incident.is_closed
        ]
        if not live:
            return None
        return max(live, key=lambda incident: (incident.opened_at, incident.incident_id))

    async def find_by_run(self, run_id: str) -> Incident | None:
        """Return the incident ``run_id`` is attached to, or ``None``."""
        for incident in self.state.incidents.values():
            if run_id in incident.run_ids:
                return incident
        return None

    async def query(self, query: IncidentQuery) -> tuple[Incident, ...]:
        """Return the incidents matching ``query``, most recently opened first."""
        limit = check_incident_limit(query.limit)
        found = [incident for incident in self.state.incidents.values() if matches(incident, query)]
        found.sort(key=lambda incident: (incident.opened_at, incident.incident_id), reverse=True)
        return tuple(found[:limit])

    async def append(self, entries: tuple[TimelineEntry, ...]) -> tuple[TimelineEntry, ...]:
        """Append ``entries`` to their incidents' timelines and return them."""
        for entry in entries:
            self.state.incident_timeline[entry.entry_id] = entry
        return entries

    async def timeline(
        self,
        incident_id: str,
        *,
        limit: int = MAX_INCIDENT_TIMELINE,
    ) -> tuple[TimelineEntry, ...]:
        """Return ``incident_id``'s history, oldest first."""
        check_timeline_limit(limit)
        found = [
            entry
            for entry in self.state.incident_timeline.values()
            if entry.incident_id == incident_id
        ]
        found.sort(key=lambda entry: (entry.at, entry.entry_id))
        return tuple(found[:limit])

    async def purge(self, *, before: datetime) -> int:
        """Delete incidents closed before ``before`` and return how many went."""
        expired = [
            incident_id
            for incident_id, incident in self.state.incidents.items()
            if incident.closed_at is not None and incident.closed_at < before
        ]
        for incident_id in expired:
            del self.state.incidents[incident_id]
        for entry_id in [
            key
            for key, entry in self.state.incident_timeline.items()
            if entry.incident_id in set(expired)
        ]:
            del self.state.incident_timeline[entry_id]
        return len(expired)


__all__ = ["FakeIncidentStore"]
