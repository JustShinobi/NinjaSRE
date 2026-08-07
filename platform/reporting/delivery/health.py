"""Which destinations have stopped working, and when to try them again.

A destination that quietly stopped accepting reports is worse than one that
never worked: the second is noticed while somebody is setting it up, and the
first is noticed the morning after the incident nobody was told about.

Two decisions.

**Consecutive failures, not total.** A destination that failed twice last month
and has worked since is working. Counting for ever would mark a healthy
destination unhealthy on the anniversary of an outage.

**Unhealthy expires.** A destination stays marked for a cooldown and is then
tried again, rather than needing an operator to clear it. A rotated token starts
working on its own, and a state that only a human can reset is a state that stays
set long after the cause is gone — usually until the next incident finds it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.notifications import (
    DESTINATION_UNHEALTHY_AFTER_FAILURES,
    DESTINATION_UNHEALTHY_COOLDOWN_SECONDS,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DestinationStatus:
    """What is known about one destination's recent behaviour."""

    destination: str
    consecutive_failures: int = 0
    last_failure_at: datetime | None = None
    last_failure_reason: str = ""
    last_success_at: datetime | None = None

    def unhealthy_at(self, at: datetime, *, threshold: int, cooldown_seconds: float) -> bool:
        """Return whether this destination is still inside an unhealthy window."""
        if self.consecutive_failures < threshold or self.last_failure_at is None:
            return False
        return (at - self.last_failure_at).total_seconds() < cooldown_seconds

    def to_record(self) -> dict[str, Any]:
        """Return the shape an operator-facing report shows."""
        return {
            "destination": self.destination,
            "consecutive_failures": self.consecutive_failures,
            "last_failure_at": (self.last_failure_at.isoformat() if self.last_failure_at else None),
            "last_failure_reason": self.last_failure_reason,
            "last_success_at": (self.last_success_at.isoformat() if self.last_success_at else None),
        }


@dataclass(slots=True)
class DestinationHealth:
    """The recent history of every destination this deployment delivers to."""

    threshold: int = DESTINATION_UNHEALTHY_AFTER_FAILURES
    cooldown_seconds: float = DESTINATION_UNHEALTHY_COOLDOWN_SECONDS
    clock: Callable[[], datetime] = _utc_now
    statuses: dict[str, DestinationStatus] = field(default_factory=dict)

    def record_success(self, destination: str) -> None:
        """Record that ``destination`` took a report, clearing its failure streak."""
        self.statuses[destination] = DestinationStatus(
            destination=destination,
            consecutive_failures=0,
            last_success_at=self.clock(),
        )

    def record_failure(self, destination: str, *, reason: str) -> None:
        """Record that ``destination`` refused a report, and say so once it is unhealthy."""
        at = self.clock()
        current = self.statuses.get(destination, DestinationStatus(destination=destination))
        updated = DestinationStatus(
            destination=destination,
            consecutive_failures=current.consecutive_failures + 1,
            last_failure_at=at,
            last_failure_reason=reason,
            last_success_at=current.last_success_at,
        )
        self.statuses[destination] = updated
        if updated.consecutive_failures == self.threshold:
            logger.error(
                "reporting.destination_unhealthy",
                destination=destination,
                consecutive_failures=updated.consecutive_failures,
                reason=reason,
            )

    def status(self, destination: str) -> DestinationStatus:
        """Return what is known about ``destination``."""
        return self.statuses.get(destination, DestinationStatus(destination=destination))

    def is_available(self, destination: str, *, at: datetime | None = None) -> bool:
        """Return whether ``destination`` should be delivered to right now."""
        moment = at if at is not None else self.clock()
        return not self.status(destination).unhealthy_at(
            moment, threshold=self.threshold, cooldown_seconds=self.cooldown_seconds
        )

    def unhealthy(self, *, at: datetime | None = None) -> tuple[DestinationStatus, ...]:
        """Return every destination currently marked unhealthy, name-ordered."""
        moment = at if at is not None else self.clock()
        return tuple(
            sorted(
                (
                    status
                    for status in self.statuses.values()
                    if status.unhealthy_at(
                        moment, threshold=self.threshold, cooldown_seconds=self.cooldown_seconds
                    )
                ),
                key=lambda status: status.destination,
            )
        )

    def report(self, *, at: datetime | None = None) -> Mapping[str, Any]:
        """Return what a health endpoint says about report delivery.

        Names the unhealthy destinations rather than counting them. "Two
        destinations are unhealthy" sends an operator to look for which two,
        which is the work this is meant to save them.
        """
        moment = at if at is not None else self.clock()
        failing = self.unhealthy(at=moment)
        return {
            "destinations": len(self.statuses),
            "unhealthy": [status.destination for status in failing],
            "detail": [status.to_record() for status in failing],
        }


__all__ = ["DestinationHealth", "DestinationStatus"]
