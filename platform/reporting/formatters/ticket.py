"""The report as an issue body: what to do, then why, then the evidence.

A ticket exists because somebody is going to act on it, and a ticket that opens
with a causal chain is a ticket whose acceptance criteria are three screens down.
So the recommended actions come directly after the conclusion, and the working
follows them.

Covers Jira, GitHub, GitLab, and a PagerDuty incident note. The four differ in
their markup dialect and in almost nothing else about the shape of an issue, and
the differences that remain — Jira's own wiki syntax, PagerDuty's plain text —
are handled by the transport that speaks to the vendor rather than by a fourth
copy of this file.
"""

from __future__ import annotations

from platform.reporting.formatters.markdown import render_section
from platform.reporting.formatters.sections import (
    SECTION_ACTIONS,
    SECTION_ROOT_CAUSE,
    SECTION_SUMMARY,
    sections,
)
from platform.reporting.models import (
    Destination,
    DestinationClass,
    FormattedReport,
    Report,
    ReportBlock,
)

#: The order an issue body reads in. Anything not named keeps its canonical
#: position after these.
_LEADING = (SECTION_SUMMARY, SECTION_ROOT_CAUSE, SECTION_ACTIONS)


class TicketFormatter:
    """Renders a report as the body of an issue or an incident note."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""
        return DestinationClass.TICKET

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as the issue body ``destination`` receives."""
        built = {
            section.key: section for section in sections(report, audience=destination.audience)
        }
        ordered = [built.pop(key) for key in _LEADING if key in built]
        ordered.extend(built.values())

        blocks = [ReportBlock(key="headline", text=f"# {report.title}")]
        blocks.extend(
            ReportBlock(key=section.key, text=render_section(section)) for section in ordered
        )
        return FormattedReport(
            destination=destination.name,
            destination_class=self.destination_class,
            title=report.title,
            body="\n\n".join(block.text for block in blocks),
            link=report.metadata.run_link,
            blocks=tuple(blocks),
        )


__all__ = ["TicketFormatter"]
