"""How many notifications one team may be sent in a window, across every sink.

Per team rather than per sink, and that is the whole design decision. A human's
attention is the scarce resource, and it is not five times less scarce because
five sinks are configured — a per-sink limit would let a team with Pushover,
email, PagerDuty, chat, and a webhook receive five times the notifications and
call it bounded.

The limit is a ceiling on *attention*, so it is checked once per notification
rather than once per delivery: one notification reaching four sinks is one
interruption.

Every refusal is recorded, for the same reason every suppression is. "You were
not told because your team had already had twenty notifications this hour" is an
answer; silence is not.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.notifications import (
    MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW,
    NOTIFICATION_RATE_LIMIT_WINDOW_SECONDS,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Whether a team has attention left in this window, and how much."""

    team_node_id: str
    allowed: bool
    used: int
    limit: int
    resets_at: datetime | None = None

    @property
    def remaining(self) -> int:
        """Return how many notifications are left in this window."""
        return max(self.limit - self.used, 0)

    def describe(self) -> str:
        """Return the sentence an operator reads."""
        if self.allowed:
            return (
                f"{self.team_node_id} has used {self.used} of {self.limit} notifications "
                f"in this window."
            )
        resets = f" until {self.resets_at.isoformat()}" if self.resets_at else ""
        return (
            f"{self.team_node_id} has had its {self.limit} notifications for this window; "
            f"further ones are held{resets}."
        )


@dataclass(slots=True)
class RateLimiter:
    """A sliding window of notification times, per team."""

    window_seconds: float = NOTIFICATION_RATE_LIMIT_WINDOW_SECONDS
    limit: int = MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW
    clock: Callable[[], datetime] = _utc_now
    sent: dict[str, list[datetime]] = field(default_factory=dict)
    refused: dict[str, int] = field(default_factory=dict)

    def check(self, team_node_id: str, *, at: datetime | None = None) -> RateLimitDecision:
        """Return whether ``team_node_id`` may be notified right now.

        Checking does not spend the allowance. A notification that is then
        suppressed by the cooldown, or that reaches no sink, must not count
        against a limit on attention nobody spent.
        """
        moment = at if at is not None else self.clock()
        within = self._within(team_node_id, moment)
        allowed = len(within) < self.limit
        if not allowed:
            self.refused[team_node_id] = self.refused.get(team_node_id, 0) + 1
            logger.info(
                "notifications.rate_limited",
                team=team_node_id,
                used=len(within),
                limit=self.limit,
            )
        return RateLimitDecision(
            team_node_id=team_node_id,
            allowed=allowed,
            used=len(within),
            limit=self.limit,
            resets_at=(
                within[0] + timedelta(seconds=self.window_seconds)
                if within and not allowed
                else None
            ),
        )

    def record(self, team_node_id: str, *, at: datetime | None = None) -> None:
        """Spend one of ``team_node_id``'s notifications for this window."""
        moment = at if at is not None else self.clock()
        held = self._within(team_node_id, moment)
        self.sent[team_node_id] = [*held, moment]

    def report(self, *, at: datetime | None = None) -> Mapping[str, Any]:
        """Return what an operator is shown about notification volume.

        Names the teams that hit the limit. A team that is being rate-limited is
        a team whose alerting is producing more than a person can act on, and
        that is a tuning problem somebody should be told about rather than a
        counter nobody reads.
        """
        moment = at if at is not None else self.clock()
        return {
            "window_seconds": self.window_seconds,
            "limit": self.limit,
            "used": {
                team: len(self._within(team, moment))
                for team in sorted(self.sent)
                if self._within(team, moment)
            },
            "rate_limited_teams": sorted(self.refused),
        }

    def _within(self, team_node_id: str, at: datetime) -> list[datetime]:
        """Return the team's notifications still inside the window ending at ``at``."""
        held = self.sent.get(team_node_id)
        if not held:
            return []
        cutoff = at.timestamp() - self.window_seconds
        return [moment for moment in held if moment.timestamp() > cutoff]


__all__ = ["RateLimitDecision", "RateLimiter"]
