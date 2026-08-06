"""Agent-proposed knowledge, diffed field by field with the body kept whole.

A knowledge proposal is usually an addition rather than an edit — the agent
learned something and wrote it down — so the interesting rendering is not a
minimal diff but the document itself, laid out so a reviewer can read it before
they accept it into the corpus their next incident will search.

The body is rendered whole up to the value ceiling, and the metadata is rendered
as fields. An agent-written paragraph summarised down to "body changed" is a
paragraph nobody read before it became something the next investigation quotes
as established fact.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from platform.approvals.diff.engine import DiffLine, DiffOperation, DiffSection, render_value

#: The fields a proposal carries, in the order a reviewer reads them: what it
#: claims, then what it is about, then what it was learned from.
DOCUMENT_FIELDS: Final[tuple[str, ...]] = (
    "title",
    "body",
    "document_type",
    "tags",
    "evidence",
    "rationale",
)

METADATA_TITLE: Final = "document"


class KnowledgeRenderer:
    """Renders a knowledge proposal as its document fields."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return one section holding every field the proposal sets or alters."""
        lines: list[DiffLine] = []
        for name in (*DOCUMENT_FIELDS, *_extra(current, proposed)):
            was, becomes = current.get(name), proposed.get(name)
            if was == becomes:
                continue
            lines.append(_line(name, was, becomes))
        return (DiffSection(title=METADATA_TITLE, lines=tuple(lines)),) if lines else ()


def _line(name: str, was: Any, becomes: Any) -> DiffLine:
    """Return the line for one document field."""
    if was is None:
        return DiffLine(path=name, operation=DiffOperation.ADDED, after=render_value(becomes))
    if becomes is None:
        return DiffLine(path=name, operation=DiffOperation.REMOVED, before=render_value(was))
    return DiffLine(
        path=name,
        operation=DiffOperation.CHANGED,
        before=render_value(was),
        after=render_value(becomes),
    )


def _extra(current: Mapping[str, Any], proposed: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the fields a proposal carries that this renderer does not name.

    Rendered rather than dropped. A field added to the proposal shape later
    would otherwise be invisible in review from the day it shipped until
    somebody noticed, and "the reviewer did not see it" is not a defect anybody
    finds by reading a renderer.
    """
    known = set(DOCUMENT_FIELDS)
    return tuple(sorted((current.keys() | proposed.keys()) - known))


__all__ = ["KnowledgeRenderer"]
