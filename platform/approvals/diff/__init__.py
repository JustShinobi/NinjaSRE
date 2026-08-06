"""Turning a proposed change into something a human can decide about.

Three pieces, in the order a review uses them: an engine that produces a
structured diff for whichever change type this is, a set of renderers that know
what "a path" means for each, and a summariser that keeps a very large diff
reviewable without ever pretending it is smaller than it is.
"""

from __future__ import annotations

from platform.approvals.diff.engine import (
    DiffEngine,
    DiffLine,
    DiffOperation,
    DiffRenderer,
    DiffSection,
    StructuredDiff,
    render_value,
)
from platform.approvals.diff.renderers import RENDERERS
from platform.approvals.diff.summarise import (
    DiffSummary,
    SummarisedSection,
    summarise,
    summary_of,
)

__all__ = [
    "RENDERERS",
    "DiffEngine",
    "DiffLine",
    "DiffOperation",
    "DiffRenderer",
    "DiffSection",
    "DiffSummary",
    "StructuredDiff",
    "SummarisedSection",
    "render_value",
    "summarise",
    "summary_of",
]
