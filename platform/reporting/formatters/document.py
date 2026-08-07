"""The report as a postmortem page, in the shape a team already reviews.

Confluence, Notion, and Google Docs are all places where a postmortem lives
next to other postmortems, gets read a month later by somebody who was not on
call, and is searched by heading. So the headings here are the ones a postmortem
template uses — "Timeline", "What we ruled out", "Follow-up" — rather than the
report's internal names, and the ordering is the one a reader expects to find
rather than the one the pipeline produced.

The content is identical to every other format. Only the labels move.
"""

from __future__ import annotations

from dataclasses import replace

from platform.reporting.formatters.markdown import render_section
from platform.reporting.formatters.sections import (
    SECTION_ACTIONS,
    SECTION_CAUSAL_CHAIN,
    SECTION_METADATA,
    SECTION_NON_VALIDATED,
    SECTION_ROOT_CAUSE,
    SECTION_RULED_OUT,
    SECTION_SUMMARY,
    SECTION_VALIDATED,
    sections,
)
from platform.reporting.models import (
    Destination,
    DestinationClass,
    FormattedReport,
    Report,
    ReportBlock,
)

#: Postmortem headings, replacing the report's own. Every key is present so a
#: section added upstream fails here loudly rather than arriving unlabelled.
POSTMORTEM_HEADINGS: dict[str, str] = {
    SECTION_SUMMARY: "Summary",
    SECTION_ROOT_CAUSE: "Root cause",
    SECTION_CAUSAL_CHAIN: "Timeline",
    SECTION_VALIDATED: "What the evidence shows",
    SECTION_NON_VALIDATED: "Open questions",
    SECTION_RULED_OUT: "What we ruled out",
    SECTION_ACTIONS: "Follow-up",
    SECTION_METADATA: "How this was investigated",
}


class DocumentFormatter:
    """Renders a report as a postmortem-shaped page."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""
        return DestinationClass.DOCUMENT

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as the page ``destination`` receives."""
        blocks = [ReportBlock(key="headline", text=f"# {report.title}")]
        for section in sections(report, audience=destination.audience):
            relabelled = replace(section, heading=POSTMORTEM_HEADINGS[section.key])
            blocks.append(ReportBlock(key=section.key, text=render_section(relabelled)))
        return FormattedReport(
            destination=destination.name,
            destination_class=self.destination_class,
            title=report.title,
            body="\n\n".join(block.text for block in blocks),
            link=report.metadata.run_link,
            blocks=tuple(blocks),
        )


__all__ = ["POSTMORTEM_HEADINGS", "DocumentFormatter"]
