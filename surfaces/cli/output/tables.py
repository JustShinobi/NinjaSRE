"""Rendering for a person, at whatever width the terminal actually has.

Two renderings of one table, chosen by width rather than by taste. Above the
readable floor it is a table; below it, each row becomes a block of labelled
lines. A four-column table squeezed into a 40-column window is not a narrower
table — it is a column of fragments, and the operator reading it at 03:00 is
the reason that is not acceptable.

Everything here takes a ``Terminal`` and holds no global state, so "what does
this look like on a dumb terminal" is a test that constructs one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from rich.box import ASCII, SIMPLE
from rich.console import Console
from rich.table import Table

from surfaces.cli.output.degradation import PLAIN, Terminal

#: What one column boundary costs: a space of padding on each side and the
#: separator between them. Three, and it has to match what the renderer
#: actually emits — a width computed against a different number produces a
#: table that is correct arithmetically and wraps on the terminal.
_COLUMN_GAP = 3

#: The narrowest a column may be squeezed to. Below this a column shows the
#: first letter of a value and an ellipsis, which is a column that costs width
#: and carries no information.
_MINIMUM_COLUMN = 8


@dataclass(frozen=True, slots=True)
class Column:
    """One column of a table, and how it behaves when space runs out.

    ``weight`` decides who gives up width first. An identifier column that
    truncated would produce values nothing can be looked up by, so it carries
    the lowest weight and shrinks last; a free-text column carries the highest
    and absorbs the loss.
    """

    header: str
    weight: int = 1

    @property
    def key(self) -> str:
        """Return the record key this column reads."""
        return self.header.lower().replace(" ", "_")


def truncate(text: str, width: int, *, terminal: Terminal = PLAIN) -> str:
    """Return ``text`` fitted into ``width``, marked when something was cut.

    Marked, because a value silently shortened to look complete is worse than
    one that is visibly not: an operator copying a truncated run identifier
    gets an error, and an operator copying one that ended in an ellipsis knows
    to widen the window.
    """
    flat = " ".join(text.split())
    if len(flat) <= width:
        return flat

    mark = terminal.glyph("ellipsis")
    if width <= len(mark):
        return flat[:width]
    return flat[: width - len(mark)] + mark


def _console(terminal: Terminal) -> Console:
    """Return a rich console configured for what ``terminal`` can render."""
    return Console(
        width=terminal.width,
        no_color=not terminal.colour,
        force_terminal=terminal.colour or None,
        legacy_windows=False,
        highlight=False,
        soft_wrap=False,
        markup=False,
        emoji=False,
    )


def _cell(value: object, terminal: Terminal) -> str:
    """Return the string a value is shown as."""
    if isinstance(value, bool):
        return terminal.glyph("ok") if value else terminal.glyph("failed")
    if value is None:
        return ""
    if isinstance(value, list | tuple):
        return ", ".join(str(element) for element in value)
    return str(value)


def _column_widths(
    columns: Sequence[Column],
    rows: Sequence[Sequence[str]],
    *,
    available: int,
) -> list[int]:
    """Return how wide each column gets, weighted by who can afford to shrink.

    Natural widths first. Only when they do not fit does weight matter, and
    then the overflow is taken from the columns that declared they can carry
    it — which is what keeps an identifier intact while a description gives way.
    """
    natural = [
        max(len(column.header), *(len(row[index]) for row in rows)) if rows else len(column.header)
        for index, column in enumerate(columns)
    ]
    gaps = _COLUMN_GAP * (len(columns) - 1)
    if sum(natural) + gaps <= available:
        return natural

    budget = max(available - gaps, len(columns))
    floors = [min(len(column.header), _MINIMUM_COLUMN) for column in columns]

    # Served lightest-weight first, each taking what it needs but never what the
    # columns behind it still have to have. That ordering is the whole of the
    # rule: an identifier is satisfied before a description is considered, so
    # the loss lands on the column that declared it could carry it.
    widths = list(floors)
    remaining = budget
    order = sorted(range(len(columns)), key=lambda index: columns[index].weight)
    for position, index in enumerate(order):
        reserved = sum(floors[later] for later in order[position + 1 :])
        widths[index] = min(natural[index], max(floors[index], remaining - reserved))
        remaining -= widths[index]

    return widths


@dataclass(frozen=True, slots=True)
class TableView:
    """A table, ready to render at whatever width it is given."""

    columns: tuple[Column, ...]
    rows: tuple[tuple[str, ...], ...] = ()
    title: str = ""
    empty: str = "nothing to show"

    def render(self, terminal: Terminal = PLAIN) -> str:
        """Return this table as ``terminal`` can show it."""
        if not self.rows:
            return self.empty
        if terminal.narrow:
            return self._as_blocks(terminal)
        return self._as_table(terminal)

    def _as_table(self, terminal: Terminal) -> str:
        """Return the tabular rendering."""
        widths = _column_widths(self.columns, self.rows, available=terminal.width)
        table = Table(
            box=SIMPLE if terminal.unicode else ASCII,
            title=self.title or None,
            width=terminal.width,
            pad_edge=False,
            show_edge=False,
        )
        for column, width in zip(self.columns, widths):
            table.add_column(column.header, width=width, overflow="ignore", no_wrap=True)
        for row in self.rows:
            table.add_row(
                *(truncate(cell, width, terminal=terminal) for cell, width in zip(row, widths))
            )

        console = _console(terminal)
        with console.capture() as captured:
            console.print(table)
        return captured.get().rstrip("\n")

    def _as_blocks(self, terminal: Terminal) -> str:
        """Return one labelled block per row, for a terminal too narrow to table.

        The rendering nobody designs for and everybody eventually needs: a
        phone-width SSH session, a split pane, a container log viewer.
        """
        label_width = max(len(column.header) for column in self.columns)
        value_width = max(terminal.width - label_width - 2, 8)
        blocks: list[str] = []
        for row in self.rows:
            lines = [
                f"{column.header.ljust(label_width)}  {truncate(cell, value_width, terminal=terminal)}"
                for column, cell in zip(self.columns, row)
            ]
            blocks.append("\n".join(lines))
        separator = "\n" + terminal.glyph("horizontal") * min(terminal.width, 20) + "\n"
        head = f"{self.title}\n\n" if self.title else ""
        return head + separator.join(blocks)


def table_of(
    records: Iterable[Mapping[str, object]],
    columns: Sequence[Column],
    *,
    terminal: Terminal = PLAIN,
    title: str = "",
    empty: str = "nothing to show",
) -> TableView:
    """Return a table over ``records``, reading each column by its key."""
    rows = tuple(
        tuple(_cell(record.get(column.key), terminal) for column in columns) for record in records
    )
    return TableView(columns=tuple(columns), rows=rows, title=title, empty=empty)


@dataclass(frozen=True, slots=True)
class Detail:
    """A set of labelled values, for output a table would flatten badly."""

    pairs: tuple[tuple[str, str], ...] = ()
    title: str = ""
    sections: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def render(self, terminal: Terminal = PLAIN) -> str:
        """Return this detail as ``terminal`` can show it."""
        lines: list[str] = []
        if self.title:
            lines.extend((self.title, terminal.glyph("horizontal") * min(terminal.width, 60)))

        if self.pairs:
            label_width = max(len(label) for label, _ in self.pairs)
            value_width = max(terminal.width - label_width - 2, 8)
            lines.extend(
                f"{label.ljust(label_width)}  {truncate(value, value_width, terminal=terminal)}"
                for label, value in self.pairs
            )

        for heading, body in self.sections:
            if not body.strip():
                continue
            lines.extend(("", heading, ""))
            lines.append(body.rstrip())

        return "\n".join(lines)


def bullet_list(items: Sequence[str], *, terminal: Terminal = PLAIN, empty: str = "") -> str:
    """Return ``items`` as a bulleted list at ``terminal``'s width."""
    if not items:
        return empty
    mark = terminal.glyph("bullet")
    width = max(terminal.width - len(mark) - 1, 8)
    return "\n".join(f"{mark} {truncate(item, width, terminal=terminal)}" for item in items)


__all__ = [
    "Column",
    "Detail",
    "TableView",
    "bullet_list",
    "table_of",
    "truncate",
]
