"""The spend view: what a period cost, per team and per run.

The same document the CLI's ``cost`` command prints, rendered as a page. One
report shape and two renderers, because a console and a command that can
disagree about a bill will, and the one nobody reconciles is the one somebody
quotes in a meeting.

The incomplete-total warning is a banner rather than a footnote. A spend figure
that omits an unpriced model is a floor, and a reader has to know that before
they quote the number rather than after somebody asks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Element, element
from surfaces.console.pages.shell import (
    PageContext,
    badge,
    card,
    definitions,
    heading,
    table,
    value_or_dash,
)


def _line_cells(context: PageContext, line: Mapping[str, Any]) -> list[Any]:
    """Return one spend row's cells."""
    return [
        value_or_dash(context, line.get("label")),
        value_or_dash(context, line.get("runs")),
        value_or_dash(context, line.get("total_tokens")),
        value_or_dash(context, line.get("cost")),
        badge(
            context.text("cost.complete" if line.get("complete") else "cost.floor"),
            kind="" if line.get("complete") else "attention",
        ),
    ]


def totals_panel(context: PageContext, report: Mapping[str, Any]) -> Element:
    """Return the headline figure and the window it covers."""
    total = report.get("total") or {}
    return card(
        heading(2, context.text("cost.total")),
        definitions(
            [
                (context.text("cost.window"), _window(context, report)),
                (context.text("cost.runs"), value_or_dash(context, total.get("runs"))),
                (context.text("cost.tokens"), value_or_dash(context, total.get("total_tokens"))),
                (context.text("cost.amount"), value_or_dash(context, total.get("cost"))),
            ]
        ),
        *(
            ()
            if total.get("complete", True)
            else (
                element(
                    "p",
                    context.text("cost.floor_warning").format(runs=total.get("unpriced_runs", 0)),
                    class_="notice notice--attention",
                ),
            )
        ),
    )


def breakdown(
    context: PageContext,
    lines: Sequence[Mapping[str, Any]],
    *,
    caption_key: str,
    first_column_key: str,
    empty_key: str,
) -> Element:
    """Return one breakdown table — by team, or by run."""
    return card(
        table(
            caption=context.text(caption_key),
            columns=[
                context.text(first_column_key),
                context.text("cost.column.runs"),
                context.text("cost.column.tokens"),
                context.text("cost.column.cost"),
                context.text("cost.column.completeness"),
            ],
            rows=[_line_cells(context, line) for line in lines],
            empty=context.text(empty_key),
        )
    )


def cost_body(context: PageContext, report: Mapping[str, Any]) -> Element:
    """Return the whole spend page for one report document."""
    return element(
        "div",
        heading(1, context.text("cost.heading")),
        totals_panel(context, report),
        breakdown(
            context,
            report.get("by_team") or [],
            caption_key="cost.by_team",
            first_column_key="cost.column.team",
            empty_key="cost.empty",
        ),
        breakdown(
            context,
            report.get("by_run") or [],
            caption_key="cost.by_run",
            first_column_key="cost.column.run",
            empty_key="cost.empty",
        ),
    )


def _window(context: PageContext, report: Mapping[str, Any]) -> str:
    """Return the period this report covers, in words."""
    since = str(report.get("since") or "")
    until = str(report.get("until") or "")
    if since and until:
        return f"{since[:10]} — {until[:10]}"
    if since:
        return context.text("cost.since").format(date=since[:10])
    if until:
        return context.text("cost.until").format(date=until[:10])
    return context.text("cost.all_time")


__all__ = ["breakdown", "cost_body", "totals_panel"]
