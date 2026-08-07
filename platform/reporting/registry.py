"""Destination class to formatter, and the one call that renders through it.

The registry is closed and complete: a mapping with an entry for every member of
``DestinationClass``, asserted by a test rather than left to a lookup that would
return ``None`` at delivery time. That is what makes adding the fourteenth
destination a row in ``DESTINATION_CLASS_OF`` and nothing else.

``render`` is the only sanctioned path from a report to a body. It formats *and*
fits, in that order, so a caller cannot reach a formatter directly and deliver
something over a destination's limit — the failure mode being a vendor that
silently accepts the first two thousand characters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from platform.reporting.formatters.chat import ChatFormatter
from platform.reporting.formatters.document import DocumentFormatter
from platform.reporting.formatters.email import EmailFormatter
from platform.reporting.formatters.markdown import MarkdownFormatter
from platform.reporting.formatters.ticket import TicketFormatter
from platform.reporting.models import (
    Destination,
    DestinationClass,
    FormattedReport,
    Report,
)
from platform.reporting.sizing import fit_to_destination


@runtime_checkable
class Formatter(Protocol):
    """Renders a report for one destination class."""

    @property
    def destination_class(self) -> DestinationClass:
        """Return the class this formatter renders."""

    def format(self, report: Report, destination: Destination) -> FormattedReport:
        """Return ``report`` as ``destination`` receives it, before fitting."""


FORMATTERS: Mapping[DestinationClass, Formatter] = {
    DestinationClass.CHAT: ChatFormatter(),
    DestinationClass.TICKET: TicketFormatter(),
    DestinationClass.DOCUMENT: DocumentFormatter(),
    DestinationClass.MARKDOWN: MarkdownFormatter(),
    DestinationClass.EMAIL: EmailFormatter(),
}


def formatter_for(destination: Destination) -> Formatter:
    """Return the formatter that renders ``destination``."""
    return FORMATTERS[destination.destination_class]


def render(report: Report, destination: Destination, *, link: str = "") -> FormattedReport:
    """Return ``report`` rendered for ``destination`` and fitted to its limit.

    ``link`` defaults to the report's own run link, which is where a summarised
    delivery points. A deployment that publishes reports somewhere else — an
    object store, a wiki — passes that address instead.
    """
    formatted = formatter_for(destination).format(report, destination)
    return fit_to_destination(formatted, destination, link=link or report.metadata.run_link)


__all__ = ["FORMATTERS", "Formatter", "formatter_for", "render"]
