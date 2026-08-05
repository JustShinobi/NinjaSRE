"""The structured conclusion, with the claims separated by whether they hold up.

Article I is the whole of this module. A claim is a sentence the model wrote;
a *validated* claim is a sentence with at least one evidence entry behind it
that the run actually holds. Keeping the two in separate fields rather than
flagging one boolean is deliberate — a report that renders
``validated_claims`` cannot accidentally render a hypothesis as a finding,
because the hypothesis is not in the field it is reading.

``validity_score`` is arithmetic over that split rather than something the
model was asked for. A model asked to score its own confidence in its own
claims answers high, consistently, and the number is worth nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from core.domain.diagnosis.taxonomy import TAXONOMY_VERSION, RootCauseCategory, category_for


@dataclass(frozen=True, slots=True)
class Claim:
    """One statement the diagnosis makes, and what it rests on.

    ``evidence_ids`` are the run's own identifiers. A claim citing an
    identifier the run does not hold is not partially right — the model
    invented a reference, and validation demotes it.
    """

    statement: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("a claim must say something")
        object.__setattr__(self, "statement", self.statement.strip())
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(str(item).strip() for item in self.evidence_ids if str(item).strip()),
        )

    def backed_by(self, held: frozenset[str]) -> bool:
        """Return whether at least one cited entry is among the ``held`` identifiers."""
        return bool(set(self.evidence_ids) & held)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this claim."""
        return {"statement": self.statement, "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Claim:
        """Return the claim a stored record describes."""
        return cls(
            statement=str(record["statement"]),
            evidence_ids=tuple(str(item) for item in record.get("evidence_ids") or ()),
        )


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """The structured conclusion one investigation produced.

    ``fallback_used`` and ``taxonomy_version`` are on the value rather than in
    a side channel because both change how the result should be read, and a
    corpus assembled from stored diagnoses has to be able to see them.
    """

    root_cause: str = ""
    root_cause_category: RootCauseCategory = RootCauseCategory.UNKNOWN
    causal_chain: tuple[str, ...] = ()
    validated_claims: tuple[Claim, ...] = ()
    non_validated_claims: tuple[Claim, ...] = ()
    remediation_steps: tuple[str, ...] = ()
    confidence: float = 0.0
    summary: str = ""
    taxonomy_version: str = TAXONOMY_VERSION
    fallback_used: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def validity_score(self) -> float:
        """Return the share of this diagnosis's claims that evidence backs.

        Computed, never asked for. A model scoring its own claims answers high
        every time, which makes the number decoration rather than a measurement.
        A diagnosis with no claims scores zero: it asserted nothing, so nothing
        about it is supported.
        """
        total = len(self.validated_claims) + len(self.non_validated_claims)
        if total == 0:
            return 0.0
        return len(self.validated_claims) / total

    @property
    def claims(self) -> tuple[Claim, ...]:
        """Return every claim, validated ones first."""
        return self.validated_claims + self.non_validated_claims

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this diagnosis."""
        return {
            "root_cause": self.root_cause,
            "root_cause_category": self.root_cause_category.value,
            "causal_chain": list(self.causal_chain),
            "validated_claims": [claim.to_record() for claim in self.validated_claims],
            "non_validated_claims": [claim.to_record() for claim in self.non_validated_claims],
            "remediation_steps": list(self.remediation_steps),
            "confidence": self.confidence,
            "validity_score": self.validity_score,
            "summary": self.summary,
            "taxonomy_version": self.taxonomy_version,
            "fallback_used": self.fallback_used,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Diagnosis:
        """Return the diagnosis a stored record describes.

        ``validity_score`` is present in the record for anything reading it as
        data and is not read back here: it is derived, and rebuilding it from
        the claims is what keeps a hand-edited record from claiming a score its
        own claims do not support.
        """
        return cls(
            root_cause=str(record.get("root_cause", "")),
            root_cause_category=category_for(str(record.get("root_cause_category", ""))),
            causal_chain=tuple(str(item) for item in record.get("causal_chain") or ()),
            validated_claims=tuple(
                Claim.from_record(item) for item in record.get("validated_claims") or ()
            ),
            non_validated_claims=tuple(
                Claim.from_record(item) for item in record.get("non_validated_claims") or ()
            ),
            remediation_steps=tuple(str(item) for item in record.get("remediation_steps") or ()),
            confidence=float(record.get("confidence", 0.0)),
            summary=str(record.get("summary", "")),
            taxonomy_version=str(record.get("taxonomy_version", TAXONOMY_VERSION)),
            fallback_used=bool(record.get("fallback_used", False)),
        )


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """One destination the report was sent to, and whether it arrived.

    Failure is a value here for the same reason it is one in the capability
    layer: a destination that raised must not stop the others, and an operator
    reading the trace needs to know which of the four got the report.
    """

    destination: str
    delivered: bool = False
    failure: str = ""
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this attempt."""
        return {
            "destination": self.destination,
            "delivered": self.delivered,
            "failure": self.failure,
            "detail": self.detail,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> DeliveryAttempt:
        """Return the attempt a stored record describes."""
        return cls(
            destination=str(record["destination"]),
            delivered=bool(record.get("delivered", False)),
            failure=str(record.get("failure", "")),
            detail=str(record.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """What delivery achieved across every configured destination."""

    attempts: tuple[DeliveryAttempt, ...] = field(default_factory=tuple)

    @property
    def delivered(self) -> tuple[str, ...]:
        """Return the destinations that received the report."""
        return tuple(item.destination for item in self.attempts if item.delivered)

    @property
    def failed(self) -> tuple[str, ...]:
        """Return the destinations that did not."""
        return tuple(item.destination for item in self.attempts if not item.delivered)

    @property
    def complete(self) -> bool:
        """Return whether every configured destination received the report."""
        return bool(self.attempts) and not self.failed

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this outcome."""
        return {"attempts": [item.to_record() for item in self.attempts]}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> DeliveryOutcome:
        """Return the outcome a stored record describes."""
        return cls(
            attempts=tuple(
                DeliveryAttempt.from_record(item) for item in record.get("attempts") or ()
            )
        )


def split_claims(claims: Sequence[Claim], held: frozenset[str]) -> tuple[tuple[Claim, ...], ...]:
    """Return ``claims`` partitioned into backed and unbacked, order preserved."""
    backed = tuple(claim for claim in claims if claim.backed_by(held))
    unbacked = tuple(claim for claim in claims if not claim.backed_by(held))
    return backed, unbacked


__all__ = [
    "Claim",
    "DeliveryAttempt",
    "DeliveryOutcome",
    "Diagnosis",
    "split_claims",
]
