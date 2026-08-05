"""Classification, field extraction, the incident window, and deduplication."""

from __future__ import annotations

from core.pipeline.stages.intake.dedup import DeduplicationResult, deduplicate
from core.pipeline.stages.intake.node import IntakeStage
from core.pipeline.stages.intake.window import derive_window

__all__ = [
    "DeduplicationResult",
    "IntakeStage",
    "deduplicate",
    "derive_window",
]
