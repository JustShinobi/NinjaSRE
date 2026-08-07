"""The console's spend view renders the same document the CLI prints.

One report shape and two renderers. The assertion that matters is not that the
page has a table — it is that an incomplete total is announced on the page
rather than left to be inferred from a column. A spend figure that omits an
unpriced model is a floor, and a reader has to know that before they quote it.
"""

from __future__ import annotations

import pytest

from platform.identity.permissions import Role
from surfaces.console.html import text_of
from surfaces.console.pages.cost import cost_body
from tests.unit.surfaces.console.conftest import SPEND, context_for

pytestmark = pytest.mark.unit


def rendered(report: object = SPEND) -> str:
    """Return the spend page's text for one report document."""
    return text_of(cost_body(context_for(Role.OWNER, path="/cost"), report))  # type: ignore[arg-type]


def test_the_period_is_stated_on_the_page() -> None:
    assert "2026-08-01 — 2026-08-31" in rendered()


def test_a_report_with_no_window_says_what_it_covers_anyway() -> None:
    """A total whose period lives in somebody's head is two different numbers."""
    assert "Every recorded run" in rendered({**SPEND, "since": "", "until": ""})


def test_an_open_ended_window_is_described_rather_than_left_blank() -> None:
    assert "Since 2026-08-01" in rendered({**SPEND, "until": ""})
    assert "Up to 2026-08-31" in rendered({**SPEND, "since": ""})


def test_both_breakdowns_are_rendered() -> None:
    text = rendered()

    assert "By team" in text
    assert "By run" in text
    assert "payments" in text
    assert "run-1" in text


def test_an_incomplete_total_is_announced_rather_than_implied() -> None:
    text = rendered()

    assert "1 run(s) used a model with no published price" in text
    assert "floor, not a bill" in text


def test_a_complete_total_carries_no_warning() -> None:
    complete = {**SPEND, "total": {**SPEND["total"], "unpriced_runs": 0, "complete": True}}  # type: ignore[dict-item]

    assert "floor, not a bill" not in rendered(complete)


def test_each_row_says_whether_its_own_figure_is_complete() -> None:
    """The team-level view has to carry it too, or the warning is unattributable."""
    text = rendered()

    assert text.count("Floor") >= 1
    assert "Complete" in text


def test_an_empty_period_renders_the_empty_state_rather_than_a_blank_table() -> None:
    empty = {**SPEND, "by_team": [], "by_run": []}

    assert "Nothing was spent in this period." in rendered(empty)


def test_a_report_missing_its_sections_entirely_still_renders() -> None:
    """A payload from an older deployment must not take the page down."""
    assert "Spend" in rendered({})
