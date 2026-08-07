"""Who is told, by which route, and — recorded just as carefully — who is not.

Four gates in a fixed order, and the order is the design.

1. **Severity and outcome choose the sinks.** A critical unresolved outcome
   reaches the paging sinks; a medium one reaches chat; noise reaches nobody and
   is recorded as having reached nobody.
2. **Quiet hours divert rather than drop.** A non-critical notification inside
   the window comes off the paging sinks and goes to the ones that do not wake
   anybody. It is still there in the morning. A critical outcome overrides the
   window entirely, because quiet hours are about sleep and not about severity.
3. **The cooldown suppresses repeats**, per team, per subject, per severity —
   and records every one.
4. **The rate limit bounds the team's total**, across every sink, because one
   notification reaching four sinks is one interruption.

The gates are checked in that order because each is cheaper and more specific
than the next, and because a notification that routes nowhere must not spend a
team's rate-limit allowance on an interruption nobody had.

Nothing here sends anything. Routing produces a decision and a list of sinks;
delivering is `service.py`'s job, which is what keeps "who should be told" a pure
function that a test can drive through a week of clock time in milliseconds.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

from config.constants.notifications import (
    QUIET_HOURS_END_HOUR,
    QUIET_HOURS_START_HOUR,
)
from platform.notifications.cooldown import Cooldown
from platform.notifications.limits import RateLimiter
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationRecord,
    NotificationSink,
    Outcome,
    Severity,
    SinkKind,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Which sink kinds each severity is willing to reach. Read as "at most": a team
#: that has not configured a kind simply does not have it, and a severity never
#: reaches a kind that is not in its row.
SEVERITY_ROUTING: dict[Severity, tuple[SinkKind, ...]] = {
    Severity.CRITICAL: (
        SinkKind.PAGERDUTY,
        SinkKind.PUSHOVER,
        SinkKind.CHAT,
        SinkKind.WEBHOOK,
    ),
    Severity.HIGH: (SinkKind.PUSHOVER, SinkKind.CHAT, SinkKind.WEBHOOK),
    Severity.MEDIUM: (SinkKind.CHAT, SinkKind.WEBHOOK),
    Severity.LOW: (SinkKind.CHAT, SinkKind.EMAIL, SinkKind.WEBHOOK),
    Severity.NOISE: (),
}


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class QuietHours:
    """When a team does not want to be woken for anything but a critical outcome.

    Expressed in the team's own timezone, because "22:00 to 07:00" means the
    team's night and a platform that evaluated it in UTC would wake a team in
    Auckland at lunchtime and never wake one in Los Angeles.
    """

    start_hour: int = QUIET_HOURS_START_HOUR
    end_hour: int = QUIET_HOURS_END_HOUR
    timezone: str = "UTC"
    enabled: bool = True

    def __post_init__(self) -> None:
        for hour in (self.start_hour, self.end_hour):
            if not 0 <= hour <= 23:
                raise ValueError(f"a quiet-hours boundary must be an hour of the day, got {hour}")

    @property
    def zone(self) -> tzinfo:
        """Return the timezone this window is expressed in."""
        return ZoneInfo(self.timezone)

    def covers(self, at: datetime) -> bool:
        """Return whether ``at`` falls inside the quiet window.

        Handles the window that wraps midnight, which is the only shape anybody
        actually configures — a window from 22:00 to 07:00 is two intervals in
        clock arithmetic and one interval to the person who wrote it.
        """
        if not self.enabled:
            return False
        hour = at.astimezone(self.zone).hour
        if self.start_hour == self.end_hour:
            return False
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


@dataclass(frozen=True, slots=True)
class Routing:
    """What the policy decided, and the sinks that follow from it."""

    notification: Notification
    sinks: tuple[NotificationSink, ...] = ()
    records: tuple[NotificationRecord, ...] = ()
    diverted: bool = False

    @property
    def sends(self) -> bool:
        """Return whether anybody is going to be told."""
        return bool(self.sinks)

    @property
    def decision(self) -> NotificationDecision:
        """Return the decision this routing represents.

        The first non-sending decision when there is one; ``DIVERTED`` when quiet
        hours moved it; ``SENT`` otherwise. A caller wanting the full picture
        reads ``records``, which has one entry per thing that happened.
        """
        for record in self.records:
            if record.decision not in (NotificationDecision.SENT, NotificationDecision.DIVERTED):
                return record.decision
        if self.diverted:
            return NotificationDecision.DIVERTED
        return NotificationDecision.SENT if self.sends else NotificationDecision.NO_SINK


@dataclass(slots=True)
class NotificationPolicy:
    """Decides which of a team's sinks a notification reaches, and records why not."""

    sinks: tuple[NotificationSink, ...] = ()
    quiet_hours: QuietHours | None = None
    cooldown: Cooldown = field(default_factory=Cooldown)
    limits: RateLimiter = field(default_factory=RateLimiter)
    clock: Callable[[], datetime] = _utc_now

    def route(self, notification: Notification, *, at: datetime | None = None) -> Routing:
        """Return which sinks ``notification`` reaches, and a record of every decision."""
        moment = at if at is not None else self.clock()
        records: list[NotificationRecord] = []

        chosen = self._by_severity(notification)
        if not chosen:
            return Routing(
                notification=notification,
                records=(
                    self._record(
                        notification,
                        NotificationDecision.NO_SINK,
                        moment,
                        reason=self._no_sink_reason(notification),
                    ),
                ),
            )

        chosen, diverted = self._apply_quiet_hours(notification, chosen, moment)
        if diverted:
            records.append(
                self._record(
                    notification,
                    NotificationDecision.DIVERTED,
                    moment,
                    reason="quiet hours: routed away from the paging sinks",
                )
            )
        if not chosen:
            records.append(
                self._record(
                    notification,
                    NotificationDecision.NO_SINK,
                    moment,
                    reason="quiet hours left no non-paging sink to route to",
                )
            )
            return Routing(notification=notification, records=tuple(records), diverted=diverted)

        suppression = self.cooldown.check(notification, at=moment)
        if suppression is not None:
            records.append(
                self._record(
                    notification,
                    NotificationDecision.SUPPRESSED,
                    moment,
                    reason=suppression.describe(),
                )
            )
            return Routing(notification=notification, records=tuple(records), diverted=diverted)

        allowance = self.limits.check(notification.team_node_id, at=moment)
        if not allowance.allowed:
            records.append(
                self._record(
                    notification,
                    NotificationDecision.RATE_LIMITED,
                    moment,
                    reason=allowance.describe(),
                )
            )
            return Routing(notification=notification, records=tuple(records), diverted=diverted)

        return Routing(
            notification=notification,
            sinks=chosen,
            records=tuple(records),
            diverted=diverted,
        )

    def commit(self, routing: Routing, *, at: datetime | None = None) -> None:
        """Spend the cooldown window and the rate-limit allowance for ``routing``.

        Separate from ``route`` so a caller can decide and then find out that
        every sink failed. Opening a fifteen-minute quiet window on a
        notification that reached nobody is how an outage in one vendor becomes
        an outage in the notification system.
        """
        if not routing.sends:
            return
        moment = at if at is not None else self.clock()
        self.cooldown.record_sent(routing.notification, at=moment)
        self.limits.record(routing.notification.team_node_id, at=moment)

    def _by_severity(self, notification: Notification) -> tuple[NotificationSink, ...]:
        """Return the configured sinks this severity and outcome route to."""
        if notification.outcome is Outcome.NOISE:
            return ()
        allowed = SEVERITY_ROUTING[notification.severity]
        if notification.outcome is Outcome.RESOLVED:
            # A resolved outcome is worth saying and not worth waking anybody
            # for, whatever the incident's severity was while it was open.
            allowed = tuple(kind for kind in allowed if not kind.pages)
        return tuple(sink for sink in self.sinks if sink.enabled and sink.kind in allowed)

    def _apply_quiet_hours(
        self,
        notification: Notification,
        chosen: Sequence[NotificationSink],
        at: datetime,
    ) -> tuple[tuple[NotificationSink, ...], bool]:
        """Return the sinks left after quiet hours, and whether anything was moved."""
        if self.quiet_hours is None or not self.quiet_hours.covers(at):
            return tuple(chosen), False
        if notification.severity is Severity.CRITICAL:
            return tuple(chosen), False
        remaining = tuple(sink for sink in chosen if not sink.pages)
        if len(remaining) == len(chosen):
            return remaining, False
        logger.info(
            "notifications.quiet_hours_diversion",
            subject=notification.subject,
            severity=notification.severity.value,
            team=notification.team_node_id,
        )
        return remaining, True

    def _no_sink_reason(self, notification: Notification) -> str:
        """Return why nothing was routed to."""
        if notification.outcome is Outcome.NOISE:
            return "the outcome was classified as noise, so nobody was notified"
        if not SEVERITY_ROUTING[notification.severity]:
            return f"{notification.severity.value} notifications route to no sink"
        return (
            f"this team has no enabled sink of a kind that "
            f"{notification.severity.value} notifications route to"
        )

    def _record(
        self,
        notification: Notification,
        decision: NotificationDecision,
        at: datetime,
        *,
        reason: str,
        sink: str = "",
    ) -> NotificationRecord:
        """Return one decision record."""
        return NotificationRecord(
            subject=notification.subject,
            severity=notification.severity,
            decision=decision,
            sink=sink,
            reason=reason,
            team_node_id=notification.team_node_id,
            run_id=notification.run_id,
            at=at,
        )


__all__ = ["SEVERITY_ROUTING", "NotificationPolicy", "QuietHours", "Routing"]
