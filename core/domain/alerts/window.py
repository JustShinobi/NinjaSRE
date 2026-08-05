"""The span every time-bounded call downstream is held to.

One type, and one property worth stating: the confidence is part of it. A
window derived from timestamps the alert carried and a window that is the
default span because nothing said when the incident began are the same two
datetimes with entirely different standing, and a report that presents the
second as the first is presenting a guess as a measurement.

Derivation lives in the intake stage. This is only the value, so anything that
needs to reason about a window — a capability argument clamp, a report header,
an evaluation answer key — can do it without importing a stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.investigation import (
    DEFAULT_INCIDENT_WINDOW_MINUTES,
    DERIVED_WINDOW_CONFIDENCE,
    FALLBACK_WINDOW_CONFIDENCE,
)


@dataclass(frozen=True, slots=True)
class IncidentWindow:
    """When the incident is taken to have happened, and how sure anyone is.

    ``derivation`` is prose naming what the window was built from. It is what an
    operator reads when a log query came back empty and the next question is
    whether the window was wrong.
    """

    start: datetime
    end: datetime
    confidence: float = DERIVED_WINDOW_CONFIDENCE
    derivation: str = ""

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("an incident window must carry timezone-aware timestamps")
        if self.end < self.start:
            raise ValueError(f"incident window ends before it starts: {self.start} .. {self.end}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"window confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

    @property
    def duration(self) -> timedelta:
        """Return how long the window spans."""
        return self.end - self.start

    @property
    def is_fallback(self) -> bool:
        """Return whether this window is the defaulted span rather than a derived one."""
        return self.confidence <= FALLBACK_WINDOW_CONFIDENCE

    def contains(self, moment: datetime) -> bool:
        """Return whether ``moment`` falls inside the window, both ends included."""
        return self.start <= moment <= self.end

    def clamp(self, moment: datetime) -> datetime:
        """Return ``moment`` moved to the nearest end of the window it falls outside."""
        if moment < self.start:
            return self.start
        if moment > self.end:
            return self.end
        return moment

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this window."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "confidence": self.confidence,
            "derivation": self.derivation,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> IncidentWindow:
        """Return the window a stored record describes."""
        return cls(
            start=datetime.fromisoformat(str(record["start"])),
            end=datetime.fromisoformat(str(record["end"])),
            confidence=float(record.get("confidence", DERIVED_WINDOW_CONFIDENCE)),
            derivation=str(record.get("derivation", "")),
        )

    @classmethod
    def default_ending_at(cls, end: datetime, *, derivation: str) -> IncidentWindow:
        """Return the defaulted span, recorded at the low confidence it deserves."""
        return cls(
            start=end - timedelta(minutes=DEFAULT_INCIDENT_WINDOW_MINUTES),
            end=end,
            confidence=FALLBACK_WINDOW_CONFIDENCE,
            derivation=derivation,
        )


def as_utc(moment: datetime) -> datetime:
    """Return ``moment`` in UTC, treating a naive timestamp as already being UTC.

    Vendors are inconsistent about offsets and several send naive strings that
    are UTC by convention. Rejecting those would fail intake on a payload an
    operator cannot change; assuming a local zone would silently shift every
    window by the deployment's offset.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


__all__ = [
    "IncidentWindow",
    "as_utc",
]
