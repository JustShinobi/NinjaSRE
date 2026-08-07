"""One formatter per destination class, over one shared set of sections.

Five modules, thirteen destinations. A formatter owns markup and ordering and
nothing else: what a section contains, and what an audience may be shown of it,
is decided once in ``sections.py`` so a new destination cannot become a new place
for the "ruled out" section to go missing.
"""

from __future__ import annotations

from platform.reporting.formatters.chat import ChatFormatter
from platform.reporting.formatters.document import DocumentFormatter
from platform.reporting.formatters.email import EmailFormatter
from platform.reporting.formatters.markdown import MarkdownFormatter
from platform.reporting.formatters.sections import Section, sections
from platform.reporting.formatters.ticket import TicketFormatter

__all__ = [
    "ChatFormatter",
    "DocumentFormatter",
    "EmailFormatter",
    "MarkdownFormatter",
    "Section",
    "TicketFormatter",
    "sections",
]
