"""Keeping the same subject quiet for a while, and writing down every time it did.

The window is per team, per subject, and per severity. Severity is in the key
because an incident that was medium an hour ago and is critical now is not the
same notification, and suppressing the second because of the first is exactly the
failure a cooldown is supposed to prevent rather than cause.

**Every suppression is recorded.** That is the whole feature. A cooldown that
quietly drops notifications is indistinguishable, from the outside, from a
notification system that is broken — and the first time anybody looks is after an
incident nobody was told about, which is the worst possible moment to be unable
to answer "was I not told, or did it not fire?".

The record is bounded. It exists to answer a question about the recent past, and
an unbounded list keyed by subject is a slow leak driven by exactly the teams
that are noisiest.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from config.constants.notifications import (
    CRITICAL_NOTIFICATION_COOLDOWN_SECONDS,
    MAX_RETAINED_SUPPRESSIONS,
    NOTIFICATION_COOLDOWN_SECONDS,
)
from platform.notifications.models import Notification, Severity
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Suppression:
    """One notification that was not sent, and what would have been said."""

    subject: str
    severity: Severity
    team_node_id: str
    title: str
    at: datetime
    until: datetime
    run_id: str = ""

    def describe(self) -> str:
        """Return the sentence an operator asking "why wasn't I told" reads."""
        return (
            f"{self.title} was suppressed at {self.at.isoformat()}: another notification "
            f"about {self.subject} ({self.severity.value}) had already been sent, and the "
            f"cooldown runs until {self.until.isoformat()}."
        )


@dataclass(slots=True)
class Cooldown:
    """Per-subject suppression windows, with every suppression kept."""

    window_seconds: float = NOTIFICATION_COOLDOWN_SECONDS
    critical_window_seconds: float = CRITICAL_NOTIFICATION_COOLDOWN_SECONDS
    max_retained: int = MAX_RETAINED_SUPPRESSIONS
    clock: Callable[[], datetime] = _utc_now
    sent: dict[str, datetime] = field(default_factory=dict)
    suppressions: list[Suppression] = field(default_factory=list)

    def window_for(self, severity: Severity) -> float:
        """Return the quiet window a notification of ``severity`` opens.

        A critical outcome gets a shorter window rather than none. A flapping
        check must not page ten times a minute, and a genuinely worsening
        incident must not be silenced for a quarter of an hour.
        """
        if severity is Severity.CRITICAL:
            return self.critical_window_seconds
        return self.window_seconds

    def check(
        self, notification: Notification, *, at: datetime | None = None
    ) -> Suppression | None:
        """Return the suppression this notification incurs, or ``None`` to send it.

        Recording happens here rather than in the caller. A suppression the
        caller had to remember to write down is a suppression that eventually
        goes unrecorded on one of the paths.
        """
        moment = at if at is not None else self.clock()
        last = self.sent.get(notification.fingerprint)
        if last is None:
            return None

        until = last + timedelta(seconds=self.window_for(notification.severity))
        if moment >= until:
            return None

        suppression = Suppression(
            subject=notification.subject,
            severity=notification.severity,
            team_node_id=notification.team_node_id,
            title=notification.title,
            at=moment,
            until=until,
            run_id=notification.run_id,
        )
        self._retain(suppression)
        logger.info(
            "notifications.suppressed",
            subject=notification.subject,
            severity=notification.severity.value,
            team=notification.team_node_id,
            until=until.isoformat(),
        )
        return suppression

    def record_sent(self, notification: Notification, *, at: datetime | None = None) -> None:
        """Open a quiet window for this notification's subject."""
        self.sent[notification.fingerprint] = at if at is not None else self.clock()

    def suppressions_for(self, team_node_id: str) -> tuple[Suppression, ...]:
        """Return what one team was not told, oldest first."""
        return tuple(item for item in self.suppressions if item.team_node_id == team_node_id)

    def recent(self, limit: int = 20) -> Sequence[Suppression]:
        """Return the most recent suppressions, newest first."""
        return tuple(reversed(self.suppressions[-limit:]))

    def _retain(self, suppression: Suppression) -> None:
        """Keep ``suppression``, dropping the oldest once the record is full."""
        self.suppressions.append(suppression)
        if len(self.suppressions) > self.max_retained:
            del self.suppressions[: len(self.suppressions) - self.max_retained]


__all__ = ["Cooldown", "Suppression"]
