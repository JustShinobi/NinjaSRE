"""Keeping a large diff reviewable, without ever pretending it is smaller.

The rule this module exists to enforce: **summarise, never truncate silently.**
A ten-thousand-line diff cut off at line two hundred looks exactly like a
two-hundred-line diff. The reviewer approves what they were shown, the remaining
nine thousand eight hundred lines apply unread, and nothing in the record says
that happened.

So a summary states three things a truncation does not:

- that it *is* a summary — ``is_summarised`` is on the value, not inferred from
  a line count somebody has to compare against a constant;
- exactly how many lines it left out, per section and in total;
- how to get them — ``drill_down`` returns any section whole, which is what
  makes "show me the rest" an operation rather than a request to a colleague.

The unit of omission is the section, not the line. Dropping every other line out
of a flat list produces something that reads as complete and is not; dropping
whole sections and naming them produces something a reviewer can navigate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.security import DIFF_SUMMARY_SECTION_LINES, DIFF_SUMMARY_THRESHOLD_LINES
from platform.approvals.diff.engine import DiffSection, StructuredDiff


@dataclass(frozen=True, slots=True)
class SummarisedSection:
    """One section of a summary, and what was left out of it."""

    title: str
    lines: tuple[str, ...] = field(default_factory=tuple)
    omitted: int = 0

    @property
    def is_complete(self) -> bool:
        """Return whether this section is shown whole."""
        return self.omitted == 0

    def render(self) -> tuple[str, ...]:
        """Return the section's heading, its lines, and its omission notice.

        The notice is a rendered line rather than a field a caller may forget to
        display. Every surface that shows a summary shows the fact that it is
        one, because the surface that forgot would be the one where a diff was
        approved unread.
        """
        heading = f"{self.title}:" if self.is_complete else f"{self.title} ({self.omitted} more):"
        tail = (f"  … {self.omitted} further change(s) in {self.title}",) if self.omitted else ()
        return (heading, *self.lines, *tail)


@dataclass(frozen=True, slots=True)
class DiffSummary:
    """A large diff, reduced to something reviewable, saying what it reduced.

    ``full`` is carried rather than discarded. Drill-down has to be answerable
    from the summary a surface is already holding — a console that had to re-run
    the diff to expand a section would expand it against whatever the target
    says *now*, which is a different document from the one being reviewed.
    """

    full: StructuredDiff
    sections: tuple[SummarisedSection, ...] = field(default_factory=tuple)
    is_summarised: bool = False

    @property
    def total_lines(self) -> int:
        """Return how many changed paths the underlying diff describes."""
        return self.full.line_count

    @property
    def shown_lines(self) -> int:
        """Return how many lines this summary actually shows."""
        return sum(len(section.lines) for section in self.sections)

    @property
    def omitted_lines(self) -> int:
        """Return how many lines the summary leaves out, in total."""
        return sum(section.omitted for section in self.sections)

    def render(self) -> tuple[str, ...]:
        """Return the summary as lines, headed by what it is when it is one."""
        body = tuple(text for section in self.sections for text in section.render())
        if not self.is_summarised:
            return body
        return (
            f"Showing {self.shown_lines} of {self.total_lines} changes across "
            f"{len(self.sections)} section(s). Nothing has been discarded — expand any "
            f"section to see the rest.",
            *body,
        )

    def drill_down(self, title: str) -> DiffSection:
        """Return the named section whole, from the diff this summarises.

        Raises ``KeyError`` naming what is available. A drill-down that silently
        returned an empty section would be a reviewer told "there is nothing
        more here" about a section there is more in.
        """
        for section in self.full.sections:
            if section.title == title:
                return section
        available = ", ".join(section.title for section in self.full.sections)
        raise KeyError(f"No section named {title!r} in this diff. It has: {available}.")

    def to_record(self) -> dict[str, Any]:
        """Return the stored form: the summary, and the whole diff behind it.

        Both, because the audit record has to reconstruct what the reviewer saw
        *and* what they were deciding about, and those are two different things
        whenever the diff was large enough to summarise.
        """
        return {
            "is_summarised": self.is_summarised,
            "total_lines": self.total_lines,
            "shown_lines": self.shown_lines,
            "omitted_lines": self.omitted_lines,
            "sections": [
                {"title": section.title, "lines": list(section.lines), "omitted": section.omitted}
                for section in self.sections
            ],
            "diff": self.full.to_record(),
        }


def summarise(
    diff: StructuredDiff,
    *,
    threshold: int = DIFF_SUMMARY_THRESHOLD_LINES,
    per_section: int = DIFF_SUMMARY_SECTION_LINES,
) -> DiffSummary:
    """Return ``diff`` reduced to something reviewable, if it needs reducing.

    Below the threshold nothing is dropped and ``is_summarised`` is false, so a
    small diff and a summarised one are distinguishable by a caller that does
    nothing but check the flag.

    Above it, every section survives — it is the *lines within* a section that
    are capped. A summary that dropped whole sections would hide that an area
    was touched at all, which is worse than showing twenty of its two hundred
    lines: the reviewer who sees twenty knows to look, and the one who sees none
    does not know there was anything to look at.
    """
    if diff.line_count <= threshold:
        return DiffSummary(
            full=diff,
            sections=tuple(
                SummarisedSection(
                    title=section.title, lines=tuple(line.render() for line in section.lines)
                )
                for section in diff.sections
            ),
            is_summarised=False,
        )

    return DiffSummary(
        full=diff,
        sections=tuple(
            SummarisedSection(
                title=section.title,
                lines=tuple(line.render() for line in section.lines[:per_section]),
                omitted=max(len(section.lines) - per_section, 0),
            )
            for section in diff.sections
        ),
        is_summarised=True,
    )


def summary_of(sections: Mapping[str, int]) -> str:
    """Return the one line a notification carries instead of a diff.

    A chat message showing two hundred lines is a chat message nobody reads, and
    the surface's job there is to get somebody to open the review rather than to
    be the review.
    """
    if not sections:
        return "no changes"
    listed = ", ".join(f"{title} ({count})" for title, count in sorted(sections.items()))
    total = sum(sections.values())
    return f"{total} change(s): {listed}"


__all__ = ["DiffSummary", "SummarisedSection", "summarise", "summary_of"]
