"""Where a run's resumable state waits between the process that made it and the one that continues it.

The payload is opaque on purpose. ``core.agent.session.Session`` already knows
how to render itself as a JSON-safe record and how to come back from one, and
this port takes exactly that record without importing the type. Two things fall
out of that, and both are worth the small awkwardness of an untyped mapping.

Storage does not move when the runtime's state does. A field added to a session
is a change to feature 004 and to nothing here — no migration, no model, no
second definition of the same shape drifting away from the first.

And the port stays honest about what it is. A ``SessionStore`` that took a
``Session`` would be a serialiser wearing a repository's name, and the next
runtime — a subagent's private state, a replayed trace — would need a second
one. This one stores records.

The runtime's own ``core.agent.store.SessionStore`` protocol is the narrow view
of this: save and load, nothing else, because that is all the loop needs. A
thin adapter satisfies both, and neither has to know about the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One resumable conversation state, as stored.

    ``status`` is duplicated out of the payload into a column of its own. It is
    the only field anything queries on — "what is still resumable" — and reading
    it out of JSONB for every row is the difference between an index and a scan.
    """

    session_id: str
    status: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None


@runtime_checkable
class SessionStore(Protocol):
    """Resumable session state, within one tenant."""

    async def save(self, record: SessionRecord) -> SessionRecord:
        """Store ``record``, replacing any earlier state under the same id.

        Last write wins, which is correct here and nowhere else in this package:
        a session is one run's own state, so there is no second writer to lose a
        race against. Raises ``PayloadTooLarge`` above the JSONB bound.
        """

    async def load(self, session_id: str) -> SessionRecord | None:
        """Return the stored session with ``session_id``, or ``None``."""

    async def delete(self, session_id: str) -> bool:
        """Delete ``session_id`` and return whether it existed."""

    async def list_resumable(
        self,
        *,
        statuses: tuple[str, ...] = (),
        limit: int = 50,
    ) -> tuple[SessionRecord, ...]:
        """Return sessions in any of ``statuses``, least recently updated first.

        An empty ``statuses`` matches every status. Oldest first because the
        caller is looking for work that has been waiting, and the one that has
        waited longest is the one to resume.
        """


__all__ = [
    "SessionRecord",
    "SessionStore",
]
