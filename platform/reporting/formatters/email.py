"""The report as an email: HTML for the client that renders it, plain text for the rest.

Both alternatives are produced, always. A plain-text part that is missing means
a client with HTML disabled — a terminal mail reader, a corporate policy, a
screen reader — receives either nothing or a wall of markup, and the person who
finds out is on call.

**Every value is escaped.** The report is built from a model's output and from
other systems' logs, and it is delivered to a client that executes markup. That
makes this the one formatter where the escaping is a security property rather
than a rendering nicety.
"""

from __future__ import annotations

from html import escape

from platform.reporting.formatters.sections import PROSE_SECTIONS, Section, sections
from platform.reporting.models import (
    Destination,
    DestinationClass,
    FormattedReport,
    Report,
    ReportBlock,
)


class EmailFormatter:
    """Renders a report as an HTML body with a plain-text alternative."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""
        return DestinationClass.EMAIL

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as the two alternatives ``destination`` receives."""
        built = sections(report, audience=destination.audience)

        blocks = [ReportBlock(key="headline", text=f"<h1>{escape(report.title)}</h1>")]
        blocks.extend(ReportBlock(key=section.key, text=_html(section)) for section in built)

        plain = "\n\n".join(
            [report.title, *(_plain(section) for section in built)],
        )
        return FormattedReport(
            destination=destination.name,
            destination_class=self.destination_class,
            title=report.title,
            body="\n".join(block.text for block in blocks),
            plain_body=plain,
            link=report.metadata.run_link,
            blocks=tuple(blocks),
        )


def _html(section: Section) -> str:
    """Return ``section`` as escaped HTML."""
    heading = f"<h2>{escape(section.heading)}</h2>"
    if section.key in PROSE_SECTIONS:
        paragraphs = "".join(f"<p>{escape(text)}</p>" for _, text in section.lines)
        return f"{heading}{paragraphs}"

    items: list[str] = []
    depth = 0
    for line_depth, text in section.lines:
        while line_depth > depth:
            items.append("<ul>")
            depth += 1
        while line_depth < depth:
            items.append("</ul>")
            depth -= 1
        items.append(f"<li>{escape(text)}</li>")
    items.extend("</ul>" for _ in range(depth))
    return f"{heading}<ul>{''.join(items)}</ul>"


def _plain(section: Section) -> str:
    """Return ``section`` as plain text, with no markup of any kind."""
    return "\n".join([section.heading, *section.flat()])


__all__ = ["EmailFormatter"]
