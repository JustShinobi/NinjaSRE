"""The record of what was done, which nothing may edit and no sweep may delete.

This port has two write methods and neither of them changes anything: you append
an event, or you ask for events back. There is no update and no delete, and that
absence is the design. An audit trail whose port exposes a deletion path is one
refactor away from a retention pass that quietly includes it, and at that point
it has stopped being evidence and become a log.

The retention sweeper knows about this too — ``DataClass.AUDIT`` is in
``RETENTION_EXEMPT_DATA_CLASSES`` and asking to purge it raises — but the
belt-and-braces is deliberate. The constant can be edited; the missing method
has to be written.

Detail payloads are bounded like every other JSONB body. An audit event
recording the whole of a rejected request is how a table that was supposed to be
cheap becomes the largest one in the database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ActorKind(StrEnum):
    """Who performed an audited action.

    ``AGENT`` is separate from ``USER`` because the distinction is the one
    reviewers care about first: whether a human or the platform did this.
    """

    USER = "user"
    TOKEN = "token"
    AGENT = "agent"
    SYSTEM = "system"


class AuditOutcome(StrEnum):
    """How the audited action ended."""

    ALLOWED = "allowed"
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable record of something that happened.

    ``detail`` holds whatever the action needs to be reconstructible — the
    approval that authorised it, the guardrail that blocked it — and nothing
    that would be a credential if it leaked.
    """

    event_id: str
    occurred_at: datetime
    actor_kind: ActorKind
    actor_id: str
    action: str
    resource_kind: str
    resource_id: str
    outcome: AuditOutcome = AuditOutcome.ALLOWED
    detail: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class AuditRepository(Protocol):
    """Append-only audit events, within one tenant."""

    async def append(self, event: AuditEvent) -> AuditEvent:
        """Store ``event`` and return it.

        Raises ``DuplicateRecord`` if ``event_id`` has already been recorded.
        Re-appending an event is either a retry that should be idempotent at the
        caller or a bug, and treating it as an overwrite would make the second
        one invisible.
        """

    async def get(self, event_id: str) -> AuditEvent | None:
        """Return the event with ``event_id``, or ``None``."""

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
        """Return matching events, most recent first.

        Every filter that is ``None`` is not applied. ``limit`` is capped by
        ``MAX_QUERY_PAGE_SIZE`` and a larger request raises ``BoundExceeded``
        rather than returning a quietly shortened answer.
        """

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
        """Return how many events match the same filters ``query`` would apply.

        Every filter that is ``None`` is not applied, exactly as it is not in
        ``query`` — the two accept an identical set of narrowing arguments so a
        caller filtering a listing gets a total that answers the same question,
        rather than one confined only to the window. Unbounded by page size.
        """


__all__ = [
    "ActorKind",
    "AuditEvent",
    "AuditOutcome",
    "AuditRepository",
]
