"""What an investigation produced, before anybody decides how to render it.

One report per run, built once, formatted per destination. That order is the
design rather than a convenience: generating a report per destination would mean
N chances for the redaction of one of them to be wrong, and a change to what a
report says would have to be made N times.

Three invariants are enforced here rather than checked downstream.

**A validated claim carries its evidence.** Not "should" — a ``ReportClaim``
without a reference cannot be filed as validated, so there is no path by which an
unbacked assertion reaches a reader wearing the word "validated" (Article I).

**Confidence is derived, never asserted.** The band comes from the score the
diagnosis computed, so a formatter cannot promote a hedge into a finding by
choosing a friendlier word for it.

**"No conclusion" is a property, not a phrasing.** ``has_conclusion`` is what a
formatter branches on, which is why every formatter says the same thing when the
investigation did not get there — and why the "ruled out" section is what it says
instead of an apology.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from config.constants.notifications import (
    AUDIENCE_PRIVATE,
    AUDIENCE_PUBLIC,
    AUDIENCE_TEAM,
    DESTINATION_CLASS_CHAT,
    DESTINATION_CLASS_DOCUMENT,
    DESTINATION_CLASS_EMAIL,
    DESTINATION_CLASS_MARKDOWN,
    DESTINATION_CLASS_OF,
    DESTINATION_CLASS_TICKET,
    DESTINATION_SIZE_LIMITS,
    IDENTIFIER_AUTHORISED_AUDIENCES,
    REPORT_DESTINATIONS,
)

#: What a report says when the investigation reached no confident conclusion.
#: One sentence, in every format, because a reader who meets three different
#: hedges learns to read past all of them.
NO_CONCLUSION_STATEMENT: str = (
    "No confident root cause was established. What was considered and eliminated "
    "is listed below, so the next person does not have to rule it out again."
)

#: The score at or above which a conclusion is reported as high confidence, and
#: the one above which it is medium. Below the second it is low; at zero there is
#: no conclusion at all.
_HIGH_CONFIDENCE_SCORE = 0.75
_MEDIUM_CONFIDENCE_SCORE = 0.5


class Confidence(StrEnum):
    """How much weight the root cause carries, as a band a human reads."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"

    @classmethod
    def of(cls, score: float) -> Confidence:
        """Return the band ``score`` falls in."""
        if score >= _HIGH_CONFIDENCE_SCORE:
            return cls.HIGH
        if score >= _MEDIUM_CONFIDENCE_SCORE:
            return cls.MEDIUM
        if score > 0.0:
            return cls.LOW
        return cls.NONE


class Horizon(StrEnum):
    """When a recommended action is meant to be taken.

    Separate from severity. "Restart the pod" and "add a saturation alert" are
    both worth doing and only one of them is worth doing at 03:14, and a flat
    list makes the reader work that out for themselves.
    """

    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    PREVENTIVE = "preventive"


class DestinationClass(StrEnum):
    """The five rendering shapes the thirteen destinations collapse into."""

    CHAT = DESTINATION_CLASS_CHAT
    TICKET = DESTINATION_CLASS_TICKET
    DOCUMENT = DESTINATION_CLASS_DOCUMENT
    MARKDOWN = DESTINATION_CLASS_MARKDOWN
    EMAIL = DESTINATION_CLASS_EMAIL


class Audience(StrEnum):
    """Who reads what arrives at a destination.

    Two independent questions, and they are answered separately because their
    answers differ. Restoring masked identifiers turns a token back into a pod
    name and needs a readership the operator controls. Carrying evidence bodies
    is about volume of internal detail, and a status page fails that test while
    a wide internal channel passes it.
    """

    PRIVATE = AUDIENCE_PRIVATE
    TEAM = AUDIENCE_TEAM
    PUBLIC = AUDIENCE_PUBLIC

    @property
    def restores_identifiers(self) -> bool:
        """Return whether this readership may see masked identifiers put back."""
        return self.value in IDENTIFIER_AUTHORISED_AUDIENCES

    @property
    def carries_evidence(self) -> bool:
        """Return whether evidence bodies may appear at all."""
        return self is not Audience.PUBLIC


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """The pointer that turns a claim into a finding.

    Carries the identifier *and* enough to find the observation without the run
    — a formatter renders this into a link or a footnote, and a reference that
    was only an opaque id would be unusable in every destination that is not the
    console.
    """

    evidence_id: str
    capability: str = ""
    source: str = ""
    summary: str = ""
    reference: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("an evidence reference must name the entry it points at")
        object.__setattr__(self, "evidence_id", self.evidence_id.strip())

    def describe(self) -> str:
        """Return the one-line citation a formatter renders."""
        where = f" ({self.source})" if self.source else ""
        detail = f": {self.summary}" if self.summary else ""
        return f"{self.evidence_id}{where}{detail}"

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this reference."""
        return {
            "evidence_id": self.evidence_id,
            "capability": self.capability,
            "source": self.source,
            "summary": self.summary,
            "reference": self.reference,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EvidenceReference:
        """Return the reference a stored record describes."""
        return cls(
            evidence_id=str(record["evidence_id"]),
            capability=str(record.get("capability", "")),
            source=str(record.get("source", "")),
            summary=str(record.get("summary", "")),
            reference=str(record.get("reference", "")),
        )


@dataclass(frozen=True, slots=True)
class ReportClaim:
    """One statement the report makes, and what it rests on."""

    statement: str
    evidence: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("a claim must say something")
        object.__setattr__(self, "statement", self.statement.strip())

    @property
    def is_validated(self) -> bool:
        """Return whether this claim cites at least one evidence entry."""
        return bool(self.evidence)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this claim."""
        return {
            "statement": self.statement,
            "evidence": [item.to_record() for item in self.evidence],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ReportClaim:
        """Return the claim a stored record describes."""
        return cls(
            statement=str(record["statement"]),
            evidence=tuple(
                EvidenceReference.from_record(item) for item in record.get("evidence") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class RuledOut:
    """Something considered and eliminated, and why.

    The section that makes a no-conclusion report worth reading. "I could not
    determine this" saves nobody any work; "I could not determine this, and it is
    not the database, here is the graph that says so" saves the next person the
    hour it took to establish that.
    """

    hypothesis: str
    reason: str
    evidence: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.hypothesis.strip():
            raise ValueError("a ruled-out entry must name what was ruled out")
        if not self.reason.strip():
            raise ValueError(f"{self.hypothesis}: a ruled-out entry must say why")
        object.__setattr__(self, "hypothesis", self.hypothesis.strip())
        object.__setattr__(self, "reason", self.reason.strip())

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this entry."""
        return {
            "hypothesis": self.hypothesis,
            "reason": self.reason,
            "evidence": [item.to_record() for item in self.evidence],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> RuledOut:
        """Return the entry a stored record describes."""
        return cls(
            hypothesis=str(record["hypothesis"]),
            reason=str(record["reason"]),
            evidence=tuple(
                EvidenceReference.from_record(item) for item in record.get("evidence") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """One thing to do, and when it is meant to be done.

    A recommendation and nothing more. Nothing in this package executes anything
    (Article III); a change that needs doing goes through the approval path,
    which is a different feature and a different set of permissions.
    """

    action: str
    horizon: Horizon = Horizon.IMMEDIATE
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("a recommended action must say what to do")
        object.__setattr__(self, "action", self.action.strip())

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this action."""
        return {
            "action": self.action,
            "horizon": self.horizon.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> RecommendedAction:
        """Return the action a stored record describes."""
        return cls(
            action=str(record["action"]),
            horizon=Horizon(record.get("horizon", Horizon.IMMEDIATE.value)),
            rationale=str(record.get("rationale", "")),
        )


@dataclass(frozen=True, slots=True)
class ReportMetadata:
    """What the investigation cost and what it used.

    Present in every report rather than in an operator's dashboard, because the
    person deciding whether to trust a conclusion is the person who benefits from
    knowing it was reached in forty seconds off two capabilities.
    """

    run_id: str = ""
    run_link: str = ""
    capabilities_used: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_id: str = ""
    team_node_id: str = ""

    @property
    def total_tokens(self) -> int:
        """Return the token total across the run."""
        return self.prompt_tokens + self.completion_tokens

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this metadata."""
        return {
            "run_id": self.run_id,
            "run_link": self.run_link,
            "capabilities_used": list(self.capabilities_used),
            "duration_seconds": self.duration_seconds,
            "cost_usd": self.cost_usd,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "model_id": self.model_id,
            "team_node_id": self.team_node_id,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ReportMetadata:
        """Return the metadata a stored record describes."""
        return cls(
            run_id=str(record.get("run_id", "")),
            run_link=str(record.get("run_link", "")),
            capabilities_used=tuple(str(name) for name in record.get("capabilities_used") or ()),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
            cost_usd=float(record.get("cost_usd", 0.0)),
            prompt_tokens=int(record.get("prompt_tokens", 0)),
            completion_tokens=int(record.get("completion_tokens", 0)),
            model_id=str(record.get("model_id", "")),
            team_node_id=str(record.get("team_node_id", "")),
        )


@dataclass(frozen=True, slots=True)
class Report:
    """The structured investigation output, before formatting."""

    run_id: str
    title: str
    summary: str
    root_cause: str = ""
    confidence_score: float = 0.0
    causal_chain: tuple[str, ...] = ()
    validated_claims: tuple[ReportClaim, ...] = ()
    non_validated_claims: tuple[ReportClaim, ...] = ()
    ruled_out: tuple[RuledOut, ...] = ()
    recommended_actions: tuple[RecommendedAction, ...] = ()
    metadata: ReportMetadata = field(default_factory=ReportMetadata)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_score <= 1.0:
            raise ValueError(
                f"confidence_score must be between 0.0 and 1.0, got {self.confidence_score}"
            )
        unbacked = [claim.statement for claim in self.validated_claims if not claim.is_validated]
        if unbacked:
            raise ValueError(
                "a validated claim must carry the evidence behind it; these do not: "
                + "; ".join(unbacked)
            )

    @property
    def confidence(self) -> Confidence:
        """Return the band the score falls in."""
        return Confidence.of(self.confidence_score)

    @property
    def has_conclusion(self) -> bool:
        """Return whether this investigation reached a root cause it stands behind.

        Both halves are required. A root cause at zero confidence is a sentence
        the model produced under pressure to produce one, and reporting it as a
        finding is the failure mode this property exists to make unrepresentable.
        """
        return bool(self.root_cause.strip()) and self.confidence_score > 0.0

    def actions_for(self, horizon: Horizon) -> tuple[RecommendedAction, ...]:
        """Return the recommended actions for one horizon, in declared order."""
        return tuple(action for action in self.recommended_actions if action.horizon is horizon)

    @property
    def evidence_references(self) -> tuple[EvidenceReference, ...]:
        """Return every evidence entry this report cites, first mention first."""
        seen: dict[str, EvidenceReference] = {}
        for claim in self.validated_claims:
            for item in claim.evidence:
                seen.setdefault(item.evidence_id, item)
        for entry in self.ruled_out:
            for item in entry.evidence:
                seen.setdefault(item.evidence_id, item)
        return tuple(seen.values())

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this report."""
        return {
            "run_id": self.run_id,
            "title": self.title,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "confidence_score": self.confidence_score,
            "confidence": self.confidence.value,
            "has_conclusion": self.has_conclusion,
            "causal_chain": list(self.causal_chain),
            "validated_claims": [claim.to_record() for claim in self.validated_claims],
            "non_validated_claims": [claim.to_record() for claim in self.non_validated_claims],
            "ruled_out": [entry.to_record() for entry in self.ruled_out],
            "recommended_actions": [action.to_record() for action in self.recommended_actions],
            "metadata": self.metadata.to_record(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Report:
        """Return the report a stored record describes.

        ``confidence`` and ``has_conclusion`` are in the record for anything
        reading it as data and are not read back: both are derived, and rebuilding
        them is what stops a hand-edited record from claiming a band its own score
        does not support.
        """
        return cls(
            run_id=str(record["run_id"]),
            title=str(record.get("title", "")),
            summary=str(record.get("summary", "")),
            root_cause=str(record.get("root_cause", "")),
            confidence_score=float(record.get("confidence_score", 0.0)),
            causal_chain=tuple(str(step) for step in record.get("causal_chain") or ()),
            validated_claims=tuple(
                ReportClaim.from_record(item) for item in record.get("validated_claims") or ()
            ),
            non_validated_claims=tuple(
                ReportClaim.from_record(item) for item in record.get("non_validated_claims") or ()
            ),
            ruled_out=tuple(RuledOut.from_record(item) for item in record.get("ruled_out") or ()),
            recommended_actions=tuple(
                RecommendedAction.from_record(item)
                for item in record.get("recommended_actions") or ()
            ),
            metadata=ReportMetadata.from_record(record.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class Destination:
    """One configured place a report is delivered to.

    Carries no credential. The transport that reaches the vendor holds a
    tenant-scoped handle and the proxy injects the secret at the network edge,
    which is why a destination is safe to store in configuration and to print in
    a health report.
    """

    kind: str
    target: str
    audience: Audience = Audience.PRIVATE
    #: Set once somebody has proved this destination works. Delivery to an
    #: unverified destination is refused rather than attempted, because the time
    #: to discover a wrong API token is not during the incident.
    verified: bool = False
    #: Overrides the destination kind's own limit when a deployment knows better
    #: — a self-hosted GitLab with a smaller body cap, for instance.
    size_limit_override: int = 0
    options: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in DESTINATION_CLASS_OF:
            raise ValueError(
                f"{self.kind!r} is not a report destination. "
                f"Known: {', '.join(REPORT_DESTINATIONS)}."
            )
        if not self.target.strip():
            raise ValueError(f"{self.kind}: a destination must name a target to deliver to")
        object.__setattr__(self, "target", self.target.strip())

    @property
    def destination_class(self) -> DestinationClass:
        """Return the rendering shape this destination takes."""
        return DestinationClass(DESTINATION_CLASS_OF[self.kind])

    @property
    def size_limit(self) -> int:
        """Return the largest body this destination accepts, in characters."""
        return self.size_limit_override or DESTINATION_SIZE_LIMITS[self.kind]

    @property
    def name(self) -> str:
        """Return the identifier a record, a log line, and a health report use."""
        return f"{self.kind}:{self.target}"

    def delivery_key(self, run_id: str) -> str:
        """Return the idempotency key for delivering ``run_id`` here.

        Per run *and* per destination, so a retry cannot duplicate and two
        destinations of the same kind are still two deliveries.
        """
        return f"{run_id}/{self.name}"


@dataclass(frozen=True, slots=True)
class ReportBlock:
    """One rendered section, still separable from the ones around it.

    A formatter produces these and joins them into ``body``. Keeping the seam is
    what makes "summarised, never truncated" a structural property rather than a
    promise: an oversized report is refitted by *dropping whole blocks*, so there
    is no code path that can cut a sentence in half.
    """

    key: str
    text: str


@dataclass(frozen=True, slots=True)
class FormattedReport:
    """A report as one destination will receive it.

    ``plain_body`` is populated by the formatters that produce two renderings of
    the same content — email is the only one today — and is empty everywhere
    else rather than duplicating ``body``.
    """

    destination: str
    destination_class: DestinationClass
    title: str
    body: str
    plain_body: str = ""
    link: str = ""
    #: True when the body is a summary standing in for a report that did not fit.
    #: Carried on the value rather than inferred from length, because a reader
    #: downstream must be able to tell a summary from a short report.
    summarised: bool = False
    blocks: tuple[ReportBlock, ...] = ()

    @property
    def length(self) -> int:
        """Return the size of the body a limit is compared against."""
        return len(self.body)

    def with_body(self, body: str, *, summarised: bool = False) -> FormattedReport:
        """Return this rendering with a different body."""
        return FormattedReport(
            destination=self.destination,
            destination_class=self.destination_class,
            title=self.title,
            body=body,
            plain_body=self.plain_body,
            link=self.link,
            summarised=summarised or self.summarised,
            blocks=self.blocks,
        )


def evidence_index(references: Sequence[EvidenceReference]) -> Mapping[str, EvidenceReference]:
    """Return ``references`` keyed by identifier, first mention winning."""
    indexed: dict[str, EvidenceReference] = {}
    for item in references:
        indexed.setdefault(item.evidence_id, item)
    return indexed


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
    "evidence_index",
]
