"""What a specialist hands back, and why it is not a transcript.

A sub-agent that returned its conversation would put its own dead ends, its
retries, and its tool payloads into the parent's context — which is the cost the
isolation was meant to avoid. The parent would then be paying for two
investigations' worth of context to get one investigation's worth of evidence.

So the contract is a ``Finding``: what the specialist established, the
observations behind each claim, and — the part that is easy to leave out and
expensive to lose — what it could not determine. A parent that cannot tell
"the logs show no errors" from "I could not read the logs" will conclude the
wrong thing from the same finding.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from config.prompts.investigation import SUBAGENT_FINDING_SUMMARY
from core.agent.session import EvidenceEntry
from core.capability.metadata import EvidenceType


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    """One observation a specialist is resting a claim on."""

    summary: str
    source: str = ""
    reference: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this observation."""
        return {"summary": self.summary, "source": self.source, "reference": self.reference}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> FindingEvidence:
        """Return the observation a stored record describes."""
        return cls(
            summary=str(record.get("summary", "")),
            source=str(record.get("source", "")),
            reference=str(record.get("reference", "")),
        )


@dataclass(frozen=True, slots=True)
class Finding:
    """One specialist's structured answer to the task it was given."""

    subagent: str
    headline: str
    established: tuple[str, ...] = ()
    evidence: tuple[FindingEvidence, ...] = ()
    unresolved: tuple[str, ...] = ()
    failed: bool = False

    def __post_init__(self) -> None:
        if not self.subagent.strip():
            raise ValueError("a finding must name the specialist that produced it")
        if not self.headline.strip():
            raise ValueError("a finding must carry a headline the parent can read")

    def as_evidence(self, *, iteration: int, call_id: str = "") -> EvidenceEntry:
        """Return this finding as one entry in the parent's evidence.

        ``origin`` carries the specialist's name. The parent has to be able to
        say where a claim came from, and "a specialist told me" is a materially
        different provenance from "I read it".
        """
        return EvidenceEntry(
            id="",
            capability=self.subagent,
            summary=SUBAGENT_FINDING_SUMMARY.format(name=self.subagent, headline=self.headline),
            evidence_type=EvidenceType.ANALYSIS,
            source=self.subagent,
            content=self.render(),
            call_id=call_id,
            iteration=iteration,
            origin=self.subagent,
        )

    def render(self) -> str:
        """Return the finding as the text the parent's model reads."""
        lines = [self.headline]
        if self.established:
            lines.append("\nEstablished:")
            lines.extend(f"- {item}" for item in self.established)
        if self.evidence:
            lines.append("\nEvidence:")
            lines.extend(
                f"- {item.summary}"
                + (f" [{item.source}]" if item.source else "")
                + (f" ({item.reference})" if item.reference else "")
                for item in self.evidence
            )
        if self.unresolved:
            lines.append("\nNot established:")
            lines.extend(f"- {item}" for item in self.unresolved)
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this finding."""
        return {
            "subagent": self.subagent,
            "headline": self.headline,
            "established": list(self.established),
            "evidence": [item.to_record() for item in self.evidence],
            "unresolved": list(self.unresolved),
            "failed": self.failed,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Finding:
        """Return the finding a stored record describes."""
        return cls(
            subagent=str(record["subagent"]),
            headline=str(record["headline"]),
            established=tuple(str(item) for item in record.get("established") or ()),
            evidence=tuple(
                FindingEvidence.from_record(item) for item in record.get("evidence") or ()
            ),
            unresolved=tuple(str(item) for item in record.get("unresolved") or ()),
            failed=bool(record.get("failed", False)),
        )


def failed_finding(subagent: str, reason: str) -> Finding:
    """Return the finding a specialist that could not run leaves behind.

    A failed sub-agent must not fail the parent, and it must not look like a
    successful one that found nothing either — those two lead the parent to
    opposite conclusions.
    """
    return Finding(
        subagent=subagent,
        headline=f"{subagent} could not complete its task: {reason}",
        unresolved=("everything this specialist was asked to establish",),
        failed=True,
    )


def _string_array(description: str) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "description": description}


#: The schema a specialist's structured return is validated against. Paired with
#: ``SUBAGENT_SYSTEM_PROMPT``: the two change together or the change is wrong.
FINDING_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One sentence: the single most useful thing you established.",
        },
        "established": _string_array(
            "Each claim you can support with an observation you actually made."
        ),
        "evidence": {
            "type": "array",
            "description": "The observations behind the claims, each with where it came from.",
            "items": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "source": {"type": "string"},
                    "reference": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
        "unresolved": _string_array(
            "What you could not determine, and why. Never leave this out to look thorough."
        ),
    },
    "required": ["headline"],
}


def finding_from_structured(subagent: str, payload: Mapping[str, Any]) -> Finding:
    """Return the finding a structured model response describes."""
    return Finding(
        subagent=subagent,
        headline=str(payload.get("headline") or f"{subagent} reported no headline"),
        established=tuple(str(item) for item in payload.get("established") or ()),
        evidence=tuple(
            FindingEvidence(
                summary=str(item.get("summary", "")),
                source=str(item.get("source", "")),
                reference=str(item.get("reference", "")),
            )
            for item in payload.get("evidence") or ()
            if isinstance(item, Mapping)
        ),
        unresolved=tuple(str(item) for item in payload.get("unresolved") or ()),
    )


def finding_from_answer(subagent: str, answer: str, evidence: Sequence[EvidenceEntry]) -> Finding:
    """Return the finding built from a specialist's answer and what it gathered.

    The fallback path, and the one that runs by default. It needs no second
    model call, which matters: asking a specialist to restate its own answer as
    JSON spends a turn of its budget to produce information it already had.
    """
    text = answer.strip()
    headline = text.splitlines()[0].strip() if text else f"{subagent} produced no answer"
    remainder = tuple(line.strip().lstrip("-* ") for line in text.splitlines()[1:] if line.strip())
    return Finding(
        subagent=subagent,
        headline=headline,
        established=remainder,
        evidence=tuple(
            FindingEvidence(summary=entry.summary, source=entry.source, reference=entry.reference)
            for entry in evidence
        ),
    )


__all__ = [
    "FINDING_SCHEMA",
    "Finding",
    "FindingEvidence",
    "failed_finding",
    "finding_from_answer",
    "finding_from_structured",
]
