"""Recognising the alert you already have an investigation for.

An alert storm is the normal case in production: one bad deploy produces forty
notifications, and investigating each of them costs forty runs to reach the
conclusion the first one reached. Linking is the alternative, and it has one
property worth insisting on — **it is non-destructive**. The second alert is
recorded and attached to the incident the first one opened; it is never
discarded. A link that turns out to be wrong costs a look at the incident
record, and a dropped alert costs whatever it was trying to say.

The fingerprint is deliberately coarse: source, alert name, and components. A
finer one — including the exact error text, say — would fail to match the same
incident reported with a different sample line, which is the case deduplication
exists for.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from config.constants.investigation import DEDUPLICATION_WINDOW_MINUTES
from core.domain.alerts.normalisation import NormalisedAlert


def fingerprint_of(alert: NormalisedAlert) -> str:
    """Return the identity two alerts for the same incident share.

    Hashed rather than concatenated so it is a fixed-width value a store can
    index, and stable across processes because it is content-derived rather
    than object-derived.
    """
    parts = [
        alert.alert_source.value,
        alert.alert_name.strip().lower(),
        "|".join(sorted(component.strip().lower() for component in alert.components)),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class IncidentRef:
    """An investigation that already exists, as deduplication needs to see it."""

    incident_id: str
    fingerprint: str
    opened_at: datetime
    alert_name: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this reference."""
        return {
            "incident_id": self.incident_id,
            "fingerprint": self.fingerprint,
            "opened_at": self.opened_at.isoformat(),
            "alert_name": self.alert_name,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> IncidentRef:
        """Return the reference a stored record describes."""
        return cls(
            incident_id=str(record["incident_id"]),
            fingerprint=str(record["fingerprint"]),
            opened_at=datetime.fromisoformat(str(record["opened_at"])),
            alert_name=str(record.get("alert_name", "")),
        )


@dataclass(frozen=True, slots=True)
class IncidentLink:
    """This alert attached to an investigation that was already open."""

    incident_id: str
    fingerprint: str
    reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this link."""
        return {
            "incident_id": self.incident_id,
            "fingerprint": self.fingerprint,
            "reason": self.reason,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> IncidentLink:
        """Return the link a stored record describes."""
        return cls(
            incident_id=str(record["incident_id"]),
            fingerprint=str(record["fingerprint"]),
            reason=str(record.get("reason", "")),
        )


def links_to(
    alert: NormalisedAlert,
    recent: tuple[IncidentRef, ...],
    *,
    now: datetime,
    window_minutes: int = DEDUPLICATION_WINDOW_MINUTES,
) -> IncidentLink | None:
    """Return the open incident ``alert`` belongs to, or ``None`` to investigate it.

    The most recently opened match wins. Two incidents sharing a fingerprint
    means the first one was already closed and re-fired, and the alert belongs
    to the one still current.
    """
    wanted = fingerprint_of(alert)
    earliest = now - timedelta(minutes=window_minutes)
    candidates = [
        found
        for found in recent
        if found.fingerprint == wanted and earliest <= found.opened_at <= now
    ]
    if not candidates:
        return None

    newest = max(candidates, key=lambda found: found.opened_at)
    age_minutes = int((now - newest.opened_at).total_seconds() // 60)
    return IncidentLink(
        incident_id=newest.incident_id,
        fingerprint=wanted,
        reason=(
            f"same source, alert name, and components as incident {newest.incident_id}, "
            f"opened {age_minutes} minute(s) ago and still inside the "
            f"{window_minutes}-minute deduplication window"
        ),
    )


__all__ = [
    "IncidentLink",
    "IncidentRef",
    "fingerprint_of",
    "links_to",
]
