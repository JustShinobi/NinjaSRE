"""Linking an alert to the investigation that is already looking at it.

The behaviour is deliberately asymmetric. Finding a match *links* — the alert
is recorded, attached, and never discarded — while finding none *opens* a new
incident and registers it, so the next copy in the storm has something to
attach to. Registration happens whichever way the classification went, because
an alert storm's second message arrives before the first investigation has
finished.

Recording is the one thing here that is not a pure function, and it is why this
is a small module with an injected index rather than a helper inside the node.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from config.constants.investigation import DEDUPLICATION_WINDOW_MINUTES
from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.correlation.fingerprint import (
    IncidentLink,
    IncidentRef,
    fingerprint_of,
    links_to,
)
from core.pipeline.ports import IncidentIndex


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """Whether this alert opened an incident or joined one."""

    fingerprint: str
    link: IncidentLink | None = None

    @property
    def is_duplicate(self) -> bool:
        """Return whether the alert was attached to an incident already open."""
        return self.link is not None


async def deduplicate(
    alert: NormalisedAlert,
    *,
    index: IncidentIndex,
    run_id: str,
    now: datetime,
    window_minutes: int = DEDUPLICATION_WINDOW_MINUTES,
) -> DeduplicationResult:
    """Return the incident ``alert`` joins, registering a new one when it joins none.

    A duplicate is not registered a second time. Registering every copy would
    make the storm's fortieth alert link to the thirty-ninth rather than to the
    investigation that is actually running, and the incident record would be a
    chain instead of a group.
    """
    recent = tuple(await index.recent(before=now))
    link = links_to(alert, recent, now=now, window_minutes=window_minutes)
    if link is not None:
        return DeduplicationResult(fingerprint=link.fingerprint, link=link)

    fingerprint = fingerprint_of(alert)
    await index.record(
        IncidentRef(
            incident_id=run_id,
            fingerprint=fingerprint,
            opened_at=now,
            alert_name=alert.alert_name,
        )
    )
    return DeduplicationResult(fingerprint=fingerprint)


__all__ = [
    "DeduplicationResult",
    "deduplicate",
]
