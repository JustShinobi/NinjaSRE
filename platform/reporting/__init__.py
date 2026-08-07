"""Turning a finished investigation into something a human reads, where they read it.

One report per run, formatted per destination class, delivered with each
destination isolated from the others. The package boundary is the point: nothing
here knows which vendor is behind a destination — a transport does — and nothing
here decides whether somebody should be woken, which is `platform.notifications`.
"""

from __future__ import annotations

from platform.reporting.models import (
    NO_CONCLUSION_STATEMENT,
    Audience,
    Confidence,
    Destination,
    DestinationClass,
    EvidenceReference,
    FormattedReport,
    Horizon,
    RecommendedAction,
    Report,
    ReportBlock,
    ReportClaim,
    ReportMetadata,
    RuledOut,
)

__all__ = [
    "NO_CONCLUSION_STATEMENT",
    "Audience",
    "Confidence",
    "Destination",
    "DestinationClass",
    "EvidenceReference",
    "FormattedReport",
    "Horizon",
    "RecommendedAction",
    "Report",
    "ReportBlock",
    "ReportClaim",
    "ReportMetadata",
    "RuledOut",
]
