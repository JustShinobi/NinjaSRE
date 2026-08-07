"""The report as a chat message: the answer first, the working underneath.

The one ordering decision that matters here. A chat reader is looking at a phone
at 03:14 and sees the first line before they see anything else, so the first line
is the conclusion — or, when there is not one, the sentence saying so. Everything
that would be at the top of a document ("Summary", then context, then the answer)
is exactly the wrong order for a notification.

Markdown is used rather than any platform's own markup. All four chat platforms
render a usable subset of it, and the parts they disagree about — tables, nested
lists past one level — are parts this report does not use.
"""

from __future__ import annotations

from platform.reporting.formatters.markdown import render_section
from platform.reporting.formatters.sections import (
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


class ChatFormatter:
    """Renders a report as a chat message, conclusion first."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""
        return DestinationClass.CHAT

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as the message ``destination`` receives."""
        built = {
            section.key: section for section in sections(report, audience=destination.audience)
        }
        lead = built.pop(SECTION_ROOT_CAUSE)
        summary = built.pop(SECTION_SUMMARY, None)

        blocks = [
            ReportBlock(
                key=SECTION_ROOT_CAUSE,
                text="\n".join(f"*{text}*" for _, text in lead.lines),
            )
        ]
        if summary is not None:
            blocks.append(ReportBlock(key=SECTION_SUMMARY, text=summary.lines[0][1]))
        blocks.extend(
            ReportBlock(key=section.key, text=render_section(section, level=3))
            for section in built.values()
        )
        return FormattedReport(
            destination=destination.name,
            destination_class=self.destination_class,
            title=report.title,
            body="\n\n".join(block.text for block in blocks),
            link=report.metadata.run_link,
            blocks=tuple(blocks),
        )


__all__ = ["ChatFormatter"]
