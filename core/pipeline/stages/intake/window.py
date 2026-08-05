"""Deriving the span every time-bounded call downstream is held to.

Two decisions are written into this, and both are about being wrong usefully.

**The window starts before the alert did.** The interesting change almost never
happens at the instant a threshold was crossed; it happens during the deploy or
the traffic shift that preceded it. A window that starts when the alert fired
excludes the cause and includes only the symptom.

**A window nobody could derive is recorded as low confidence, not as absent.**
An absent window would leave every downstream capability picking its own range,
which is the same guess made five times with nobody able to see it. The
defaulted span is the guess made once, written down, and visible in the report
as a guess.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from config.constants.investigation import (
    DEFAULT_INCIDENT_WINDOW_MINUTES,
    DERIVED_WINDOW_CONFIDENCE,
    INCIDENT_WINDOW_LEAD_MINUTES,
)
from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.alerts.window import IncidentWindow, as_utc

#: What the derivation field says when the alert carried a start time.
DERIVED_FROM_ALERT = (
    f"the alert's own start time, less {INCIDENT_WINDOW_LEAD_MINUTES} minutes of lead so the "
    "change that caused it is inside the window"
)

#: What it says when nothing in the alert named a time.
DERIVED_FROM_DEFAULT = (
    f"nothing in the alert named when the incident began, so the default "
    f"{DEFAULT_INCIDENT_WINDOW_MINUTES}-minute span ending at intake was used"
)

#: What it says when the alert's start time is in the future. Clock skew between
#: a vendor and this deployment is common and produces a window that has not
#: happened yet, which every downstream query would return nothing for.
DERIVED_FROM_SKEWED = (
    "the alert's start time is in the future relative to this deployment, so the default "
    "span ending at intake was used instead"
)


def derive_window(alert: NormalisedAlert, *, now: datetime) -> IncidentWindow:
    """Return the incident window ``alert`` implies, defaulted when it implies none.

    The end is the alert's own end when it carried one — a resolved
    notification bounds the incident exactly — and otherwise the moment intake
    ran, because the incident is still happening.
    """
    at = as_utc(now)
    started = as_utc(alert.started_at) if alert.started_at is not None else None

    if started is None:
        return IncidentWindow.default_ending_at(at, derivation=DERIVED_FROM_DEFAULT)
    if started > at:
        return IncidentWindow.default_ending_at(at, derivation=DERIVED_FROM_SKEWED)

    ended = as_utc(alert.ended_at) if alert.ended_at is not None else at
    start = started - timedelta(minutes=INCIDENT_WINDOW_LEAD_MINUTES)
    return IncidentWindow(
        start=start,
        end=max(ended, started),
        confidence=DERIVED_WINDOW_CONFIDENCE,
        derivation=DERIVED_FROM_ALERT,
    )


__all__ = [
    "DERIVED_FROM_ALERT",
    "DERIVED_FROM_DEFAULT",
    "DERIVED_FROM_SKEWED",
    "derive_window",
]
