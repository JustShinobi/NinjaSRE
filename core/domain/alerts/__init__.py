"""Turning whatever arrived into the same shape, whoever sent it."""

from __future__ import annotations

from core.domain.alerts.normalisation import (
    NormalisedAlert,
    RawAlert,
    Severity,
    adapter_for,
    detect_source,
    normalise,
)
from core.domain.alerts.sources import ALERT_SOURCES, AlertSource
from core.domain.alerts.window import IncidentWindow

__all__ = [
    "ALERT_SOURCES",
    "AlertSource",
    "IncidentWindow",
    "NormalisedAlert",
    "RawAlert",
    "Severity",
    "adapter_for",
    "detect_source",
    "normalise",
]
