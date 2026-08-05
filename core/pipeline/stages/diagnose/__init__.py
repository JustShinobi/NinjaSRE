"""The structured-output call, the claim check, and the degraded parser."""

from __future__ import annotations

from core.pipeline.stages.diagnose.fallback import parse_conclusion
from core.pipeline.stages.diagnose.models import DIAGNOSIS_SCHEMA, diagnosis_from_structured
from core.pipeline.stages.diagnose.node import DiagnoseStage
from core.pipeline.stages.diagnose.validation import (
    unbacked_citations,
    uncited_evidence,
    validate,
)

__all__ = [
    "DIAGNOSIS_SCHEMA",
    "DiagnoseStage",
    "diagnosis_from_structured",
    "parse_conclusion",
    "unbacked_citations",
    "uncited_evidence",
    "validate",
]
