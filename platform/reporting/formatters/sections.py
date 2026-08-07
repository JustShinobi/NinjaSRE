"""The report's sections, once, in the order every destination presents them.

Five formatters render the same eight sections. Building those sections five
times would mean five places for a section to be dropped, and the one that gets
dropped is always the one nobody looks at until they need it — "what was ruled
out", in the report that reached no conclusion.

So the *content* of a section is decided here and the *syntax* is decided by the
formatter. A formatter may reorder the sections, rename their headings, and
choose its own markup; it may not invent a section and it may not silently omit
one, because it never sees the report directly.

The audience is applied here too, for the same reason. Evidence summaries are
the part of a report most likely to carry something a wide readership should not
see, and a per-formatter decision about them would be four chances to get it
wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from platform.reporting.models import (
    NO_CONCLUSION_STATEMENT,
    Audience,
    EvidenceReference,
    Horizon,
    Report,
    ReportClaim,
    RuledOut,
)

#: Section keys, in the order the plan's report-structure table lists them.
SECTION_SUMMARY = "summary"
SECTION_ROOT_CAUSE = "root_cause"
SECTION_CAUSAL_CHAIN = "causal_chain"
SECTION_VALIDATED = "validated_claims"
SECTION_NON_VALIDATED = "non_validated_claims"
SECTION_RULED_OUT = "ruled_out"
SECTION_ACTIONS = "recommended_actions"
SECTION_METADATA = "metadata"

#: The heading each section carries unless a formatter renames it.
DEFAULT_HEADINGS: dict[str, str] = {
    SECTION_SUMMARY: "Summary",
    SECTION_ROOT_CAUSE: "Root cause",
    SECTION_CAUSAL_CHAIN: "Causal chain",
    SECTION_VALIDATED: "What the evidence supports",
    SECTION_NON_VALIDATED: "Not confirmed",
    SECTION_RULED_OUT: "Ruled out",
    SECTION_ACTIONS: "Recommended actions",
    SECTION_METADATA: "Run detail",
}

#: Sections whose lines are sentences rather than list items. Everything else
#: reads as a list in every format, so a formatter bullets by membership here
#: rather than by knowing what each section is about.
PROSE_SECTIONS: frozenset[str] = frozenset({SECTION_SUMMARY, SECTION_ROOT_CAUSE})

_HORIZON_LABELS: dict[Horizon, str] = {
    Horizon.IMMEDIATE: "Immediate",
    Horizon.SHORT_TERM: "Short term",
    Horizon.PREVENTIVE: "Preventive",
}


@dataclass(frozen=True, slots=True)
class Section:
    """One section's key, its default heading, and its lines.

    ``lines`` are already flattened to strings. Nesting is expressed by
    ``indent``: a formatter renders an indented line as a sub-bullet, a
    continuation, or a smaller paragraph, and none of them has to understand the
    report's shape to do it.
    """

    key: str
    heading: str
    lines: tuple[tuple[int, str], ...] = ()

    @property
    def empty(self) -> bool:
        """Return whether this section has nothing to show."""
        return not self.lines

    def flat(self) -> tuple[str, ...]:
        """Return the lines with their indentation applied as spaces."""
        return tuple(f"{'  ' * depth}{text}" for depth, text in self.lines)


def sections(report: Report, *, audience: Audience = Audience.PRIVATE) -> tuple[Section, ...]:
    """Return every non-empty section of ``report``, in the canonical order.

    The root-cause section is never empty: an investigation that reached no
    conclusion says so there, which is what keeps a reader from having to notice
    an absence.
    """
    built = (
        _section(SECTION_SUMMARY, ((0, report.summary),) if report.summary else ()),
        _section(SECTION_ROOT_CAUSE, _root_cause_lines(report)),
        _section(SECTION_CAUSAL_CHAIN, _chain_lines(report.causal_chain)),
        _section(SECTION_VALIDATED, _claim_lines(report.validated_claims, audience)),
        _section(SECTION_NON_VALIDATED, _claim_lines(report.non_validated_claims, audience)),
        _section(SECTION_RULED_OUT, _ruled_out_lines(report.ruled_out, audience)),
        _section(SECTION_ACTIONS, _action_lines(report)),
        _section(SECTION_METADATA, _metadata_lines(report)),
    )
    return tuple(section for section in built if not section.empty)


def _section(key: str, lines: Sequence[tuple[int, str]]) -> Section:
    """Return the section ``key`` with ``lines``."""
    return Section(key=key, heading=DEFAULT_HEADINGS[key], lines=tuple(lines))


def _root_cause_lines(report: Report) -> tuple[tuple[int, str], ...]:
    """Return the root-cause section, or the sentence that stands in for it."""
    if not report.has_conclusion:
        return ((0, NO_CONCLUSION_STATEMENT),)
    return (
        (0, report.root_cause),
        (0, f"Confidence: {report.confidence.value}"),
    )


def _chain_lines(chain: Sequence[str]) -> tuple[tuple[int, str], ...]:
    """Return the causal chain, numbered so the mechanism reads in order."""
    return tuple((0, f"{index}. {step}") for index, step in enumerate(chain, start=1))


def _claim_lines(claims: Sequence[ReportClaim], audience: Audience) -> tuple[tuple[int, str], ...]:
    """Return one line per claim, each followed by its citations."""
    lines: list[tuple[int, str]] = []
    for claim in claims:
        lines.append((0, claim.statement))
        lines.extend((1, _cite(item, audience)) for item in claim.evidence)
    return tuple(lines)


def _ruled_out_lines(
    entries: Sequence[RuledOut], audience: Audience
) -> tuple[tuple[int, str], ...]:
    """Return one line per eliminated hypothesis, with why and what showed it."""
    lines: list[tuple[int, str]] = []
    for entry in entries:
        lines.append((0, f"{entry.hypothesis} — {entry.reason}"))
        lines.extend((1, _cite(item, audience)) for item in entry.evidence)
    return tuple(lines)


def _cite(item: EvidenceReference, audience: Audience) -> str:
    """Return the citation line this audience may read.

    A readership that may not see evidence bodies still gets the identifier and
    the system it came from — enough for somebody with access to go and look,
    and nothing that says what was in it.
    """
    if audience.carries_evidence:
        return item.describe()
    return f"{item.evidence_id} ({item.source})" if item.source else item.evidence_id


def _action_lines(report: Report) -> tuple[tuple[int, str], ...]:
    """Return the recommended actions, grouped by when they are meant to happen."""
    lines: list[tuple[int, str]] = []
    for horizon in Horizon:
        actions = report.actions_for(horizon)
        if not actions:
            continue
        lines.append((0, f"{_HORIZON_LABELS[horizon]}:"))
        for action in actions:
            detail = f" — {action.rationale}" if action.rationale else ""
            lines.append((1, f"{action.action}{detail}"))
    return tuple(lines)


def _metadata_lines(report: Report) -> tuple[tuple[int, str], ...]:
    """Return what the run used and what it cost."""
    metadata = report.metadata
    lines: list[tuple[int, str]] = []
    if metadata.capabilities_used:
        lines.append((0, f"Capabilities used: {', '.join(metadata.capabilities_used)}"))
    lines.append((0, f"Duration: {metadata.duration_seconds:.0f}s"))
    lines.append((0, f"Cost: ${metadata.cost_usd:.2f} over {metadata.total_tokens} tokens"))
    if metadata.model_id:
        lines.append((0, f"Model: {metadata.model_id}"))
    if metadata.run_link:
        lines.append((0, f"Run: {metadata.run_link}"))
    return tuple(lines)


__all__ = [
    "DEFAULT_HEADINGS",
    "PROSE_SECTIONS",
    "SECTION_ACTIONS",
    "SECTION_CAUSAL_CHAIN",
    "SECTION_METADATA",
    "SECTION_NON_VALIDATED",
    "SECTION_ROOT_CAUSE",
    "SECTION_RULED_OUT",
    "SECTION_SUMMARY",
    "SECTION_VALIDATED",
    "Section",
    "sections",
]
