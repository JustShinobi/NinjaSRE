"""Prompts, diffed by line.

A prompt is prose, and the only useful unit for prose is the line. Rendering a
prompt change as "``prompts.investigation`` changed from <4,200 characters> to
<4,240 characters>" is technically a diff and tells a reviewer nothing about
what an agent will now be told to do.

Every line is kept, added and removed alike, and the summariser above decides
what a long one looks like. A renderer that dropped the unchanged context would
make a two-word edit unreadable, and one that dropped changed lines would be the
silent truncation this feature exists to refuse.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

from platform.approvals.diff.engine import DiffLine, DiffOperation, DiffSection, render_value
from platform.config_service import paths


class PromptRenderer:
    """Renders each changed prompt as its added and removed lines."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return one section per prompt whose text the change would alter."""
        before = dict(paths.leaves(current))
        after = dict(paths.leaves(proposed))

        sections: list[DiffSection] = []
        for path in sorted(before.keys() | after.keys()):
            was, becomes = before.get(path), after.get(path)
            if was == becomes:
                continue
            lines = tuple(_line_diff(_text(was), _text(becomes)))
            sections.append(
                DiffSection(title=path, lines=lines if lines else (_whole(path, was, becomes),))
            )
        return tuple(sections)


def _line_diff(before: list[str], after: list[str]) -> list[DiffLine]:
    """Return the added and removed lines between two texts, in reading order."""
    found: list[DiffLine] = []
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        for offset, text in enumerate(before[before_start:before_end], start=before_start + 1):
            found.append(
                DiffLine(path=f"line {offset}", operation=DiffOperation.REMOVED, before=text)
            )
        for offset, text in enumerate(after[after_start:after_end], start=after_start + 1):
            found.append(DiffLine(path=f"line {offset}", operation=DiffOperation.ADDED, after=text))
    return found


def _whole(path: str, was: Any, becomes: Any) -> DiffLine:
    """Return a single line for a prompt that is not text at all.

    A prompt path holding a number or a list is a configuration mistake rather
    than a prompt, and showing it whole is more use to the reviewer than an
    empty section that says the value changed without saying to what.
    """
    return DiffLine(
        path=path,
        operation=DiffOperation.CHANGED,
        before=render_value(was),
        after=render_value(becomes),
    )


def _text(value: Any) -> list[str]:
    """Return ``value`` as lines, or nothing at all when it is not text."""
    return value.splitlines() if isinstance(value, str) else []


__all__ = ["PromptRenderer"]
