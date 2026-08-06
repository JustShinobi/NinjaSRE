"""Configuration, diffed by path.

A configuration document is a tree and a reviewer reasons about it as a set of
dotted paths — ``policies.masking.level``, not "line 47". So the unit is the
leaf path, and the section is the top-level key it sits under: an operator
scanning a change wants to know it touched masking and budgets before they want
to know which fields.

Removals are changes. A gated field that could be *deleted* without appearing in
the diff is a gated field in name only, and deletion is how a value quietly
falls back to whatever an ancestor says.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from platform.approvals.diff.engine import DiffLine, DiffOperation, DiffSection, render_value
from platform.config_service import paths


class ConfigurationRenderer:
    """Renders a configuration document's changed leaf paths, grouped by area."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return one section per top-level key the change touches."""
        before = dict(paths.leaves(current))
        after = dict(paths.leaves(proposed))

        grouped: dict[str, list[DiffLine]] = {}
        for path in sorted(before.keys() | after.keys()):
            if before.get(path) == after.get(path) and path in before and path in after:
                continue
            line = _line(path, before, after)
            if line is not None:
                grouped.setdefault(_area(path), []).append(line)

        return tuple(
            DiffSection(title=area, lines=tuple(lines)) for area, lines in sorted(grouped.items())
        )


def _line(path: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> DiffLine | None:
    """Return the line for ``path``, or ``None`` when nothing about it moved."""
    present_before = path in before
    present_after = path in after
    if present_before and present_after:
        if before[path] == after[path]:
            return None
        return DiffLine(
            path=path,
            operation=DiffOperation.CHANGED,
            before=render_value(before[path]),
            after=render_value(after[path]),
        )
    if present_after:
        return DiffLine(path=path, operation=DiffOperation.ADDED, after=render_value(after[path]))
    return DiffLine(path=path, operation=DiffOperation.REMOVED, before=render_value(before[path]))


def _area(path: str) -> str:
    """Return the top-level key a path sits under, which is its section."""
    head, _, _ = path.partition(".")
    return head or path


__all__ = ["ConfigurationRenderer"]
