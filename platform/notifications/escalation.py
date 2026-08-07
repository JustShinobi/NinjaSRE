"""Following up on an attention item nobody addressed — and not following up when they did.

An approval granted at minute nine must not page somebody at minute ten. That is
the whole feature: an escalation that fires after its item resolved trains people
to ignore escalations, and an escalation people ignore is worth less than none,
because it also costs the interruption.

**Cancellation is a write, and firing is a read.** ``resolve`` marks the
escalation cancelled the moment the underlying item closes; ``due`` never returns
a cancelled one. There is no window in which resolution has happened and the
escalation is still live, because both go through the same registry and the
registry is what a caller holds.

**Escalation is bounded.** An item that stays unaddressed escalates a fixed
number of times and then stops. An escalation that repeats for ever is a
notification the recipient filters, at which point the next one is also filtered.

Nothing here schedules anything with a timer. The registry answers "what is due
at this instant", and whatever drives the deployment's clock — the scheduler, a
loop, a test moving time by hand — asks it. A component that owned a timer would
be a component the suite has to sit through.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from config.constants.notifications import ESCALATION_DELAY_SECONDS, MAX_ESCALATION_ROUNDS
from platform.notifications.models import NotificationSink, Severity
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


class EscalationState(StrEnum):
    """Where one escalation is in its short life."""

    SCHEDULED = "scheduled"
    FIRED = "fired"
    #: The underlying item resolved first. Terminal, and the outcome this whole
    #: module exists to make reachable.
    CANCELLED = "cancelled"
    #: Escalated as many times as it is allowed to.
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class Escalation:
    """One attention item's pending follow-up."""

    item_id: str
    subject: str
    team_node_id: str
    sink: NotificationSink
    due_at: datetime
    severity: Severity = Severity.HIGH
    run_id: str = ""
    summary: str = ""
    round: int = 1
    state: EscalationState = EscalationState.SCHEDULED
    resolved_reason: str = ""

    @property
    def live(self) -> bool:
        """Return whether this escalation can still fire."""
        return self.state is EscalationState.SCHEDULED

    def is_due(self, at: datetime) -> bool:
        """Return whether this escalation should fire at ``at``."""
        return self.live and at >= self.due_at

    def describe(self) -> str:
        """Return the sentence the escalated notification carries."""
        return (
            f"{self.summary or self.subject} has been waiting since it was raised and "
            f"nobody has addressed it. This is escalation {self.round}."
        )


@dataclass(slots=True)
class EscalationRegistry:
    """Every pending escalation, and the two operations that end one."""

    delay_seconds: float = ESCALATION_DELAY_SECONDS
    max_rounds: int = MAX_ESCALATION_ROUNDS
    clock: Callable[[], datetime] = _utc_now
    pending: dict[str, Escalation] = field(default_factory=dict)
    history: list[Escalation] = field(default_factory=list)

    def schedule(
        self,
        item_id: str,
        *,
        subject: str,
        team_node_id: str,
        sink: NotificationSink,
        severity: Severity = Severity.HIGH,
        run_id: str = "",
        summary: str = "",
        at: datetime | None = None,
    ) -> Escalation:
        """Schedule a follow-up for ``item_id`` and return it.

        Rescheduling an item that is already pending replaces it rather than
        adding a second. Two escalations for one approval is two pages for one
        decision, and the second one arrives after somebody has already been
        woken by the first.
        """
        moment = at if at is not None else self.clock()
        escalation = Escalation(
            item_id=item_id,
            subject=subject,
            team_node_id=team_node_id,
            sink=sink,
            due_at=moment + timedelta(seconds=self.delay_seconds),
            severity=severity,
            run_id=run_id,
            summary=summary,
        )
        self.pending[item_id] = escalation
        return escalation

    def resolve(self, item_id: str, *, reason: str = "") -> Escalation | None:
        """Cancel ``item_id``'s escalation because the item itself closed.

        Returns the cancelled escalation, or ``None`` when there was nothing
        pending — resolving an item nobody escalated is the ordinary case, not an
        error, and raising for it would make every caller write the same guard.
        """
        escalation = self.pending.pop(item_id, None)
        if escalation is None:
            return None
        cancelled = replace(
            escalation,
            state=EscalationState.CANCELLED,
            resolved_reason=reason or "the underlying item resolved",
        )
        self.history.append(cancelled)
        logger.info(
            "notifications.escalation_cancelled",
            item_id=item_id,
            subject=escalation.subject,
            team=escalation.team_node_id,
            reason=cancelled.resolved_reason,
        )
        return cancelled

    def due(self, *, at: datetime | None = None) -> tuple[Escalation, ...]:
        """Return the escalations that fire now, and advance each one.

        Firing and rescheduling happen together. An escalation returned here and
        left pending would be returned again on the next tick, and the recipient
        would be paged once per tick rather than once per round.
        """
        moment = at if at is not None else self.clock()
        firing = tuple(
            sorted(
                (item for item in self.pending.values() if item.is_due(moment)),
                key=lambda item: (item.due_at, item.item_id),
            )
        )
        for escalation in firing:
            self._advance(escalation, moment)
        return tuple(replace(item, state=EscalationState.FIRED) for item in firing)

    def pending_for(self, team_node_id: str) -> tuple[Escalation, ...]:
        """Return one team's pending escalations, soonest first."""
        return tuple(
            sorted(
                (item for item in self.pending.values() if item.team_node_id == team_node_id),
                key=lambda item: item.due_at,
            )
        )

    @property
    def cancelled(self) -> tuple[Escalation, ...]:
        """Return every escalation that was cancelled by a resolution."""
        return tuple(item for item in self.history if item.state is EscalationState.CANCELLED)

    @property
    def fired(self) -> tuple[Escalation, ...]:
        """Return every escalation that actually fired, oldest first."""
        return tuple(item for item in self.history if item.state is EscalationState.FIRED)

    def _advance(self, escalation: Escalation, at: datetime) -> None:
        """Record ``escalation`` as fired and queue its next round, if it has one."""
        self.history.append(replace(escalation, state=EscalationState.FIRED))
        logger.info(
            "notifications.escalated",
            item_id=escalation.item_id,
            subject=escalation.subject,
            team=escalation.team_node_id,
            round=escalation.round,
        )
        if escalation.round >= self.max_rounds:
            self.pending.pop(escalation.item_id, None)
            self.history.append(replace(escalation, state=EscalationState.EXHAUSTED))
            return
        self.pending[escalation.item_id] = replace(
            escalation,
            round=escalation.round + 1,
            due_at=at + timedelta(seconds=self.delay_seconds),
            state=EscalationState.SCHEDULED,
        )


__all__ = ["Escalation", "EscalationRegistry", "EscalationState"]
