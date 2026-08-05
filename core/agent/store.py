"""Where a session goes between the run that started it and the one that resumes it.

A port, because storage is Postgres and Postgres belongs to
``platform/persistence/`` (Article XI). The runtime needs two operations and no
knowledge of either: put this session somewhere, and give it back by id.

The in-memory implementation is not a placeholder for tests. It is the correct
store for a run that lives inside one process — a CLI investigating something
once — and having it here means the loop's persistence path is exercised by
every test rather than being the code that only runs in production.

Saving is best-effort by design. A store that is down must not fail an
investigation that is otherwise going well: the failure is logged and the run
continues, because a completed investigation nobody persisted is worth more than
an exception where the answer would have been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.agent.session import Session
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class SessionStore(Protocol):
    """Persistence for a resumable session."""

    async def save(self, session: Session) -> None:
        """Store ``session``, replacing any earlier state under the same id."""

    async def load(self, session_id: str) -> Session | None:
        """Return the stored session with ``session_id``, or ``None``."""


@dataclass(slots=True)
class InMemorySessionStore:
    """A store that lives as long as the process does.

    Records go through ``to_record`` rather than holding the object, so a caller
    that keeps mutating a session it already saved does not silently rewrite
    history — which is exactly the bug an object cache would hide.
    """

    _records: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    async def save(self, session: Session) -> None:
        """Store ``session`` as a record."""
        self._records[session.id] = session.to_record()

    async def load(self, session_id: str) -> Session | None:
        """Return the stored session with ``session_id``, or ``None``."""
        record = self._records.get(session_id)
        return Session.from_record(record) if record is not None else None

    def __len__(self) -> int:
        return len(self._records)


async def save_quietly(store: SessionStore | None, session: Session) -> bool:
    """Save ``session`` if there is a store, and return whether it landed.

    Never raises. A store that is unreachable during an incident is a problem
    for afterwards; taking the investigation down with it is a problem now.
    """
    if store is None:
        return False
    try:
        await store.save(session)
    except Exception as error:  # noqa: BLE001 — persistence must not fail a run
        logger.warning("agent.session_not_persisted", session_id=session.id, error=str(error))
        return False
    return True


__all__ = [
    "InMemorySessionStore",
    "SessionStore",
    "save_quietly",
]
