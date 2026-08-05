"""The structured conclusion and the closed vocabulary it is written in."""

from __future__ import annotations

from core.domain.diagnosis.alignment import aligned, misalignment_note, neighbours_of
from core.domain.diagnosis.result import (
    Claim,
    DeliveryAttempt,
    DeliveryOutcome,
    Diagnosis,
    split_claims,
)
from core.domain.diagnosis.taxonomy import (
    CATEGORY_DESCRIPTIONS,
    ROOT_CAUSE_CATEGORIES,
    TAXONOMY_VERSION,
    RootCauseCategory,
    category_for,
    is_conclusive,
)

__all__ = [
    "CATEGORY_DESCRIPTIONS",
    "ROOT_CAUSE_CATEGORIES",
    "TAXONOMY_VERSION",
    "Claim",
    "DeliveryAttempt",
    "DeliveryOutcome",
    "Diagnosis",
    "RootCauseCategory",
    "aligned",
    "category_for",
    "is_conclusive",
    "misalignment_note",
    "neighbours_of",
    "split_claims",
]
