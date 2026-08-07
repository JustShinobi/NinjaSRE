"""The report as a Markdown document, which is also the canonical full version.

This is the rendering every other one is a shortening of. A destination that
imposes a size limit is delivered a summary and a link, and the link points at
this — so it is the one formatter with no notion of fitting anywhere, and the one
that must never drop a section.
"""

from __future__ import annotations

from platform.reporting.formatters.sections import PROSE_SECTIONS, Section, sections
from platform.reporting.models import (
    Destination,
    DestinationClass,
    FormattedReport,
    Report,
    ReportBlock,
)

#: The file a local Markdown destination writes. Fixed rather than derived from
#: the title: a directory of reports is browsed by run, and a filename built
#: from prose is a filename that eventually contains a slash.
REPORT_FILENAME = "report.md"


class MarkdownFormatter:
    """Renders a report as a Markdown document."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""
        return DestinationClass.MARKDOWN

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as the Markdown document ``destination`` receives."""
        blocks = [ReportBlock(key="headline", text=f"# {report.title}")]
        blocks.extend(
            ReportBlock(key=section.key, text=render_section(section))
            for section in sections(report, audience=destination.audience)
        )
        return FormattedReport(
            destination=destination.name,
            destination_class=self.destination_class,
            title=report.title,
            body="\n\n".join(block.text for block in blocks),
            link=report.metadata.run_link,
            blocks=tuple(blocks),
        )


def render_section(section: Section, *, level: int = 2) -> str:
    """Return ``section`` as a Markdown heading and its body.

    Shared with the ticket and document formatters, which are Markdown with
    different headings and a different order — copying this three times would be
    three places for a nested citation to lose its indentation.
    """
    heading = f"{'#' * level} {section.heading}"
    if section.key in PROSE_SECTIONS:
        return "\n\n".join([heading, *(text for _, text in section.lines)])
    body = "\n".join(f"{'  ' * depth}- {text}" for depth, text in section.lines)
    return f"{heading}\n\n{body}"


__all__ = ["REPORT_FILENAME", "MarkdownFormatter", "render_section"]
