"""Rendering for a person, at 80 columns and narrower.

The other half of readable-anywhere. Readability is not a property anybody can
assert directly, so what is asserted here is the three things that make output
unreadable when they go wrong: a line wider than the terminal, a value cut
without saying so, and a table rendered into a window too narrow to hold one.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import DEFAULT_TERMINAL_WIDTH, MINIMUM_TABLE_WIDTH
from surfaces.cli.output.degradation import ASCII_GLYPHS, PLAIN, Terminal
from surfaces.cli.output.tables import Column, Detail, TableView, bullet_list, table_of, truncate

pytestmark = pytest.mark.unit

_COLUMNS = (
    Column("Run id", weight=1),
    Column("Status", weight=1),
    Column("Objective", weight=6),
)

_RECORDS = (
    {
        "run_id": "run-0000000001",
        "status": "completed",
        "objective": "checkout latency doubled after the 14:02 deploy, spreading to payments",
    },
    {
        "run_id": "run-0000000002",
        "status": "running",
        "objective": "nodes in eu-west-1c reporting disk pressure",
    },
)


def _rendered(terminal: Terminal) -> list[str]:
    """Return the table's lines as ``terminal`` renders them."""
    view = table_of(_RECORDS, _COLUMNS, terminal=terminal, title="Runs")
    return view.render(terminal).splitlines()


def test_no_line_exceeds_the_terminal_width_at_eighty_columns() -> None:
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH)

    for line in _rendered(terminal):
        assert len(line) <= DEFAULT_TERMINAL_WIDTH, line


def test_no_line_exceeds_the_terminal_width_when_very_wide() -> None:
    terminal = Terminal(width=200, unicode=True)

    for line in _rendered(terminal):
        assert len(line) <= 200, line


def test_the_identifier_column_survives_when_the_description_does_not() -> None:
    # The weighting decision, asserted: an identifier that truncated would
    # produce values nothing can be looked up by.
    rendered = "\n".join(_rendered(Terminal(width=DEFAULT_TERMINAL_WIDTH)))

    assert "run-0000000001" in rendered
    assert "run-0000000002" in rendered


def test_a_narrow_terminal_gets_labelled_lines_instead_of_a_table() -> None:
    terminal = Terminal(width=MINIMUM_TABLE_WIDTH - 20)
    rendered = "\n".join(_rendered(terminal))

    # Every value keeps its label, which is what a table's header row was doing.
    assert "Run id" in rendered
    assert "Status" in rendered
    assert "run-0000000001" in rendered
    for line in rendered.splitlines():
        assert len(line) <= terminal.width, line


def test_a_cut_value_says_it_was_cut() -> None:
    cut = truncate("a" * 40, 10, terminal=PLAIN)

    assert len(cut) == 10
    assert cut.endswith(ASCII_GLYPHS["ellipsis"])


def test_a_value_that_fits_is_left_alone() -> None:
    assert truncate("short", 10) == "short"


def test_truncation_collapses_the_whitespace_it_was_given() -> None:
    # A cell holding a newline would otherwise break the row it sits in.
    assert truncate("two\n   lines", 20) == "two lines"


def test_an_empty_table_says_so_rather_than_rendering_a_header() -> None:
    view = table_of((), _COLUMNS, empty="no runs yet")

    assert view.render(PLAIN) == "no runs yet"


def test_a_bool_renders_as_the_terminals_own_glyph() -> None:
    ascii_terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, unicode=False)
    unicode_terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, unicode=True)
    columns = (Column("Name"), Column("Healthy"))
    records = ({"name": "datadog", "healthy": True},)

    assert "OK" in table_of(records, columns, terminal=ascii_terminal).render(ascii_terminal)
    assert "✓" in table_of(records, columns, terminal=unicode_terminal).render(unicode_terminal)


def test_the_ascii_rendering_is_encodable_as_ascii() -> None:
    # The rendering exists for a terminal that could not encode the other one.
    rendered = "\n".join(_rendered(Terminal(width=DEFAULT_TERMINAL_WIDTH, unicode=False)))

    rendered.encode("ascii")


def test_a_detail_block_keeps_within_the_width() -> None:
    detail = Detail(
        title="run-0000000001",
        pairs=(("Status", "completed"), ("Objective", "x" * 200)),
        sections=(("Result", "the deploy at 14:02 reduced the connection pool"),),
    )

    for line in detail.render(Terminal(width=DEFAULT_TERMINAL_WIDTH)).splitlines():
        assert len(line) <= DEFAULT_TERMINAL_WIDTH, line


def test_a_bullet_list_uses_the_terminals_glyph_and_width() -> None:
    rendered = bullet_list(["first", "second"], terminal=Terminal(width=40, unicode=False))

    assert rendered.splitlines() == ["* first", "* second"]


def test_an_empty_bullet_list_renders_its_placeholder() -> None:
    assert bullet_list([], empty="none") == "none"


def test_a_table_view_renders_the_same_values_at_every_width() -> None:
    # Width changes the layout, never the content. A value that disappeared at
    # one width would make "run it wider" a debugging step.
    for width in (40, 80, 120, 200):
        rendered = "\n".join(_rendered(Terminal(width=width)))
        assert "completed" in rendered
        assert "running" in rendered


def test_a_view_with_no_rows_at_a_narrow_width_still_says_so() -> None:
    view = TableView(columns=_COLUMNS, empty="nothing")

    assert view.render(Terminal(width=30)) == "nothing"
