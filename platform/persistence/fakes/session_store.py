"""In-memory resumable session state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.session_store import SessionRecord

#: Sorts before any real timestamp, so a never-touched session is the
#: longest-waiting one under an ascending sort — which is what it is.
_NEVER = datetime.min.replace(tzinfo=UTC)


@dataclass(slots=True)
class FakeSessionStore:
    """Session records for one organisation."""

    org_id: str
    state: TenantState

    async def save(self, record: SessionRecord) -> SessionRecord:
        """Store ``record``, replacing any earlier state under the same id."""
        check_payload(record.payload, kind="session")
        stored = (
            record
            if record.updated_at is not None
            else replace(record, updated_at=datetime.now(UTC))
        )
        self.state.sessions[record.session_id] = stored
        return stored

    async def load(self, session_id: str) -> SessionRecord | None:
        """Return the stored session with ``session_id``, or ``None``."""
        return self.state.sessions.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """Delete ``session_id`` and return whether it existed."""
        return self.state.sessions.pop(session_id, None) is not None

    async def list_resumable(
        self,
        *,
        statuses: tuple[str, ...] = (),
        limit: int = 50,
    ) -> tuple[SessionRecord, ...]:
        """Return sessions in any of ``statuses``, least recently updated first."""
        check_limit(limit)
        matches = [
            record
            for record in self.state.sessions.values()
            if not statuses or record.status in statuses
        ]
        matches.sort(key=lambda r: (r.updated_at or _NEVER, r.session_id))
        return tuple(matches[:limit])


__all__ = ["FakeSessionStore"]
