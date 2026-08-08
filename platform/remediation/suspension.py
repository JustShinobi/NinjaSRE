"""Stopping autonomous action on one resource, and the record of why.

A failed rollback is the worst state this system can reach: it has changed
something, failed to undo it, and does not know what state the resource is in.
Continuing to act on that resource unattended is the worst available option, so
it stops — per resource, visibly, until a person says otherwise.

**A suspension is two append-only rows, not a mutable flag.** One says it was
suspended, with the action that caused it and the reason; the other says a
person cleared it, with who and why. The current state is whichever is later.
That is not a storage trick — it is the shape the question actually has, because
"is this resource suspended" is only ever asked alongside "and what happened",
and a boolean column would answer the first and lose the second.

**Only a human clears one.** There is no timeout and no automatic expiry. A
suspension that lapsed on its own would resume unattended action on a resource
nobody had looked at, which is precisely the thing the suspension exists to
prevent.

**A suspension stops autonomy, not everything.** An approved action from a
person is still permitted, and has to be: somebody has to be able to fix the
resource, and the approval path is where they do it with a review in front of
them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.closed_loop import (
    CLOSED_LOOP_AUDIT_ACTION_CLEARED,
    CLOSED_LOOP_AUDIT_ACTION_SUSPENDED,
    CLOSED_LOOP_AUDIT_RESOURCE_KIND,
    MAX_SUSPENSION_ROWS,
    SUSPENSION_DETAIL_ACTION,
    SUSPENSION_DETAIL_REASON,
)
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, AuditEvent, AuditOutcome, AuditRepository
from platform.remediation.models import utc_now

_LOG = get_logger(__name__)

#: Who a suspension raised by the deployment itself is attributed to. Named once
#: so every row carries the same actor rather than whichever string a call site
#: happened to hold.
SUSPENSION_ACTOR: str = "ninjasre-remediation"


@dataclass(frozen=True, slots=True)
class Suspension:
    """One resource's current standing: suspended since when, and why.

    ``cleared_at`` being set means this is history rather than a live
    suspension. Both are returned by the same query because the listing an
    operator reads wants "suspended, and these three were cleared last week" in
    one place.
    """

    resource_id: str
    since: datetime
    reason: str
    action_id: str = ""
    cleared_at: datetime | None = None
    cleared_by: str = ""
    clear_reason: str = ""

    @property
    def is_live(self) -> bool:
        """Return whether autonomous action on this resource is stopped right now."""
        return self.cleared_at is None

    def describe(self) -> str:
        """Return the sentence an operator reads."""
        if self.is_live:
            return (
                f"Autonomous action on {self.resource_id} has been suspended since "
                f"{self.since.isoformat()}: {self.reason}"
            )
        return (
            f"{self.resource_id} was suspended at {self.since.isoformat()} and cleared by "
            f"{self.cleared_by or 'a person'}: {self.clear_reason or 'no reason given'}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the API response and the CLI both render."""
        return {
            "resource_id": self.resource_id,
            "since": self.since.isoformat(),
            "reason": self.reason,
            "action_id": self.action_id,
            "live": self.is_live,
            "cleared_at": self.cleared_at.isoformat() if self.cleared_at else None,
            "cleared_by": self.cleared_by,
            "clear_reason": self.clear_reason,
        }


@dataclass(slots=True)
class AutonomySuspensions:
    """Which resources this deployment has stopped acting on unattended.

    Derived from the audit trail rather than held in a table of its own, for the
    reason the autonomy budgets are: the trail is already append-only,
    tenant-scoped, exempt from the retention sweep, and the record of every
    decision this package makes. A suspension derived from it *is* the record,
    and a second bookkeeping table would be a second thing that can disagree
    with it — a disagreement that would only ever be discovered during an
    argument about what the system did.

    Holds the repository rather than the gateway, so suspending and recording
    the verdict that caused it land in one transaction. A service that opened
    its own unit of work could suspend a resource for a rollback failure the
    surrounding transaction then rolled back, which is the one arrangement in
    which a resource is suspended for something that did not happen.
    """

    audit: AuditRepository
    clock: Callable[[], datetime] = field(default=utc_now)
    actor_id: str = SUSPENSION_ACTOR

    async def suspend(
        self,
        resource_id: str,
        *,
        reason: str,
        action_id: str = "",
        at: datetime | None = None,
    ) -> Suspension:
        """Stop autonomous action on ``resource_id`` and return the suspension.

        Idempotent by derived identity: suspending a resource twice for the same
        action appends one row. A resource already suspended for a different
        action gets a second row, and the later one wins — which is right,
        because the newer failure is the one somebody has to read first.
        """
        if not reason.strip():
            raise ValueError(
                "A suspension must say why. An unexplained one is a resource the "
                "deployment has stopped acting on with nothing for a human to act on."
            )
        moment = at if at is not None else self.clock()
        await self._append(
            action=CLOSED_LOOP_AUDIT_ACTION_SUSPENDED,
            resource_id=resource_id,
            at=moment,
            outcome=AuditOutcome.DENIED,
            actor_kind=ActorKind.SYSTEM,
            actor_id=self.actor_id,
            detail={
                SUSPENSION_DETAIL_REASON: reason,
                SUSPENSION_DETAIL_ACTION: action_id,
            },
        )
        _LOG.error(
            "remediation.autonomy_suspended",
            resource_id=resource_id,
            action_id=action_id,
            reason=reason,
        )
        return Suspension(resource_id=resource_id, since=moment, reason=reason, action_id=action_id)

    async def clear(
        self,
        resource_id: str,
        *,
        principal_id: str,
        reason: str,
        at: datetime | None = None,
    ) -> Suspension | None:
        """Let autonomy resume on ``resource_id``, and return what was cleared.

        ``None`` when nothing was suspended — which is not an error. An operator
        clearing a resource that had already been cleared has done no harm, and
        raising would make the safe thing to do the thing that produces a stack
        trace.
        """
        if not principal_id:
            raise ValueError(
                "Clearing a suspension needs the person doing it. The whole of the "
                "control is that a human looked at the resource, and a clearing with "
                "nobody's name on it records that nobody did."
            )
        if not reason.strip():
            raise ValueError(
                "Clearing a suspension needs a reason. It is the record of what somebody "
                "found when they looked, and it is the only thing the next person has."
            )
        live = await self.current(resource_id)
        if live is None:
            return None

        moment = at if at is not None else self.clock()
        await self._append(
            action=CLOSED_LOOP_AUDIT_ACTION_CLEARED,
            resource_id=resource_id,
            at=moment,
            outcome=AuditOutcome.ALLOWED,
            actor_kind=ActorKind.USER,
            actor_id=principal_id,
            detail={SUSPENSION_DETAIL_REASON: reason},
        )
        _LOG.info(
            "remediation.autonomy_suspension_cleared",
            resource_id=resource_id,
            cleared_by=principal_id,
            reason=reason,
        )
        return Suspension(
            resource_id=live.resource_id,
            since=live.since,
            reason=live.reason,
            action_id=live.action_id,
            cleared_at=moment,
            cleared_by=principal_id,
            clear_reason=reason,
        )

    async def current(self, resource_id: str) -> Suspension | None:
        """Return the live suspension on ``resource_id``, or ``None``.

        Latest-wins over the two row kinds. A resource suspended, cleared, and
        suspended again is suspended; one suspended and then cleared is not; and
        the order is read off the instants rather than off the arrival sequence,
        because two replicas can append in either order.
        """
        rows = await self._rows(resource_id=resource_id)
        return _live_of(rows).get(resource_id)

    async def all(self, *, live_only: bool = True) -> tuple[Suspension, ...]:
        """Return every suspension, most recent first.

        The listing FR-010 means by "visible". Without it a suspension is a
        thing an operator finds out about by trying to act and being refused,
        which is the same as not being visible at all.
        """
        rows = await self._rows()
        found = _suspensions_of(rows)
        if live_only:
            found = [item for item in found if item.is_live]
        found.sort(key=lambda item: (item.since, item.resource_id), reverse=True)
        return tuple(found)

    async def _rows(self, *, resource_id: str | None = None) -> tuple[AuditEvent, ...]:
        """Return the suspension and clearing rows, newest first."""
        suspended = await self.audit.query(
            action=CLOSED_LOOP_AUDIT_ACTION_SUSPENDED,
            resource_kind=CLOSED_LOOP_AUDIT_RESOURCE_KIND,
            resource_id=resource_id,
            limit=MAX_SUSPENSION_ROWS,
        )
        cleared = await self.audit.query(
            action=CLOSED_LOOP_AUDIT_ACTION_CLEARED,
            resource_kind=CLOSED_LOOP_AUDIT_RESOURCE_KIND,
            resource_id=resource_id,
            limit=MAX_SUSPENSION_ROWS,
        )
        return (*suspended, *cleared)

    async def _append(
        self,
        *,
        action: str,
        resource_id: str,
        at: datetime,
        outcome: AuditOutcome,
        actor_kind: ActorKind,
        actor_id: str,
        detail: dict[str, Any],
    ) -> None:
        """Append one immutable row, tolerating the retry that writes it twice."""
        from platform.persistence.errors import DuplicateRecord

        event = AuditEvent(
            event_id=f"{action}:{resource_id}:{at.isoformat()}",
            occurred_at=at,
            actor_kind=actor_kind,
            actor_id=actor_id,
            action=action,
            resource_kind=CLOSED_LOOP_AUDIT_RESOURCE_KIND,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail,
        )
        try:
            await self.audit.append(event)
        except DuplicateRecord:
            # The identity is derived from the resource and the instant, so a
            # retry of the same suspension is the same row. Swallowing this is
            # the whole point of deriving it.
            _LOG.debug("remediation.suspension_row_already_recorded", event_id=event.event_id)


def _suspensions_of(rows: tuple[AuditEvent, ...]) -> list[Suspension]:
    """Return one suspension per raising row, stamped with its clearing if any."""
    raised = sorted(
        (row for row in rows if row.action == CLOSED_LOOP_AUDIT_ACTION_SUSPENDED),
        key=lambda row: row.occurred_at,
    )
    clearings = sorted(
        (row for row in rows if row.action == CLOSED_LOOP_AUDIT_ACTION_CLEARED),
        key=lambda row: row.occurred_at,
    )

    found: list[Suspension] = []
    for row in raised:
        clearing = next(
            (
                item
                for item in clearings
                if item.resource_id == row.resource_id and item.occurred_at >= row.occurred_at
            ),
            None,
        )
        found.append(
            Suspension(
                resource_id=row.resource_id,
                since=row.occurred_at,
                reason=str(row.detail.get(SUSPENSION_DETAIL_REASON, "")),
                action_id=str(row.detail.get(SUSPENSION_DETAIL_ACTION, "")),
                cleared_at=clearing.occurred_at if clearing is not None else None,
                cleared_by=clearing.actor_id if clearing is not None else "",
                clear_reason=(
                    str(clearing.detail.get(SUSPENSION_DETAIL_REASON, ""))
                    if clearing is not None
                    else ""
                ),
            )
        )
    return found


def _live_of(rows: tuple[AuditEvent, ...]) -> dict[str, Suspension]:
    """Return the live suspension per resource, keyed by resource."""
    live: dict[str, Suspension] = {}
    for item in sorted(_suspensions_of(rows), key=lambda held: held.since):
        if item.is_live:
            live[item.resource_id] = item
        else:
            live.pop(item.resource_id, None)
    return live


__all__ = [
    "SUSPENSION_ACTOR",
    "AutonomySuspensions",
    "Suspension",
]
