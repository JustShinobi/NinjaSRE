"""The schema the structured call is held to, and how its answer becomes a value.

The schema is written out rather than derived from the dataclass because the
two answer different questions. ``Diagnosis`` is what the rest of the system
reads; this is what the *model* is asked for, and the difference is deliberate
in three places:

- ``validity_score`` is absent. It is arithmetic over the claim split, and a
  model scoring its own claims answers high every time.
- Claims are one list, not two. Which of them are validated is decided against
  the evidence the run holds, not by the model's opinion of its own citations.
- Every list is bounded. A model asked for an unbounded causal chain produces
  one, and forty steps is a transcript with numbers on it (Article II).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from config.constants.investigation import (
    MAX_CAUSAL_CHAIN_STEPS,
    MAX_DIAGNOSIS_CLAIMS,
    MAX_REMEDIATION_STEPS,
)
from core.domain.diagnosis.result import Claim, Diagnosis
from core.domain.diagnosis.taxonomy import TAXONOMY_VERSION, RootCauseCategory, category_for

DIAGNOSIS_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "root_cause": {
            "type": "string",
            "description": "One or two sentences stating what caused the incident.",
        },
        "root_cause_category": {
            "type": "string",
            "enum": [member.value for member in RootCauseCategory],
            "description": (
                "The category from the closed list. Choose 'unknown' rather than the "
                "closest-sounding one when the evidence does not support attributing a cause."
            ),
        },
        "summary": {
            "type": "string",
            "description": "A short paragraph an on-call engineer can read in ten seconds.",
        },
        "causal_chain": {
            "type": "array",
            "maxItems": MAX_CAUSAL_CHAIN_STEPS,
            "items": {"type": "string"},
            "description": "The steps from cause to symptom, in order, cause first.",
        },
        "claims": {
            "type": "array",
            "maxItems": MAX_DIAGNOSIS_CLAIMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "One thing this diagnosis asserts.",
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "The identifiers of the evidence entries supporting this claim, "
                            "exactly as listed. Empty if none does — do not invent one."
                        ),
                    },
                },
                "required": ["statement", "evidence_ids"],
            },
            "description": "Every claim the diagnosis makes, supported or not.",
        },
        "remediation_steps": {
            "type": "array",
            "maxItems": MAX_REMEDIATION_STEPS,
            "items": {"type": "string"},
            "description": "Recommendations for a human. Nothing here is executed.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How sure you are of the root cause and its category.",
        },
    },
    "required": [
        "root_cause",
        "root_cause_category",
        "summary",
        "causal_chain",
        "claims",
        "remediation_steps",
        "confidence",
    ],
}


def diagnosis_from_structured(structured: Mapping[str, Any]) -> Diagnosis:
    """Return the diagnosis a structured answer describes, before validation.

    Every claim lands in ``validated_claims`` here and validation moves the
    unbacked ones out. Doing it the other way round — trusting the model's own
    split — would make Article I a request rather than a check.
    """
    return Diagnosis(
        root_cause=str(structured.get("root_cause", "")).strip(),
        root_cause_category=category_for(str(structured.get("root_cause_category", ""))),
        summary=str(structured.get("summary", "")).strip(),
        causal_chain=_lines(structured.get("causal_chain"), MAX_CAUSAL_CHAIN_STEPS),
        validated_claims=_claims(structured.get("claims")),
        remediation_steps=_lines(structured.get("remediation_steps"), MAX_REMEDIATION_STEPS),
        confidence=_confidence(structured.get("confidence")),
        taxonomy_version=TAXONOMY_VERSION,
    )


def _claims(value: object) -> tuple[Claim, ...]:
    """Return the claims ``value`` describes, malformed entries dropped."""
    if not isinstance(value, list):
        return ()

    claims: list[Claim] = []
    for item in value[:MAX_DIAGNOSIS_CLAIMS]:
        if not isinstance(item, Mapping):
            continue
        statement = str(item.get("statement", "")).strip()
        if not statement:
            continue
        raw_ids = item.get("evidence_ids")
        ids = tuple(str(found) for found in raw_ids) if isinstance(raw_ids, list) else ()
        claims.append(Claim(statement=statement, evidence_ids=ids))
    return tuple(claims)


def _lines(value: object, limit: int) -> tuple[str, ...]:
    """Return ``value`` as a bounded tuple of non-empty strings."""
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value[:limit] if (text := str(item).strip()))


def _confidence(value: object) -> float:
    """Return ``value`` as a confidence, clamped rather than rejected."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    try:
        number = float(value)
    except ValueError:
        return 0.0
    return min(1.0, max(0.0, number))


__all__ = [
    "DIAGNOSIS_SCHEMA",
    "diagnosis_from_structured",
]
