"""``ninjasre cost`` — what a period cost, and who spent it.

The report an operator takes to whoever pays for the tokens. Two breakdowns,
because the two questions are different: *which team is spending this* is a
budget conversation, and *which run cost that much* is an investigation into one
outlier.

The window is stated in the output rather than assumed. A spend figure whose
period lives in somebody's head is a number two people read as covering two
different things.

``unpriced_runs`` is reported beside the money and never folded into it. A model
with no published price contributes tokens and no cost, and a total that quietly
absorbed it understates the bill in the one direction nobody checks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import typer

from surfaces.cli.errors import CliError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import SpendLine, SpendReport
from surfaces.cli.output.tables import Column, table_of

#: How many runs a report reaches back over by default. Enough for a month of
#: an active deployment, and bounded because a remote deployment pays one
#: request per run.
DEFAULT_SPEND_RUN_LIMIT = 200

_TEAM_COLUMNS = (
    Column("Team", weight=3),
    Column("Runs", weight=1),
    Column("Tokens", weight=2),
    Column("Cost", weight=2),
    Column("Unpriced", weight=1),
)

_RUN_COLUMNS = (
    Column("Run", weight=3),
    Column("Turns", weight=1),
    Column("Tokens", weight=2),
    Column("Cost", weight=2),
)


def _moment(raw: str, *, flag: str) -> datetime | None:
    """Return the instant ``raw`` names, or nothing when it was not given.

    Raises:
        CliError: the value is not a date this command understands. Naming the
            flag matters — an operator who typed two dates should be told which
            one is wrong.
    """
    if not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as failure:
        raise CliError(
            f"{flag} {raw!r} is not a date",
            remedy="use an ISO-8601 date, such as 2026-08-01, or 2026-08-01T09:00",
        ) from failure
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _team_row(line: SpendLine) -> dict[str, str]:
    """Return one team's row."""
    return {
        "Team": line.label,
        "Runs": str(line.runs),
        "Tokens": f"{line.total_tokens:,}",
        "Cost": f"{line.cost:.4f}",
        "Unpriced": str(line.unpriced_runs) if line.unpriced_runs else "—",
    }


def _run_row(line: SpendLine) -> dict[str, str]:
    """Return one run's row."""
    return {
        "Run": line.label,
        "Turns": str(line.turns),
        "Tokens": f"{line.total_tokens:,}",
        "Cost": f"{line.cost:.4f}",
    }


def report_text(report: SpendReport, invocation: Invocation) -> str:
    """Return the human rendering of a spend report."""
    window = " to ".join(part for part in (_shown(report.since), _shown(report.until)) if part)
    blocks = [
        f"Spend {window}" if window else "Spend, all recorded runs",
        "",
        f"{report.total.runs} runs, {report.total.total_tokens:,} tokens, {report.total.cost:.4f}",
    ]
    if not report.total.is_complete:
        # Stated rather than starred: the reader has to know the number is a
        # floor before they quote it, not after somebody asks.
        blocks.append(
            f"{report.total.unpriced_runs} run(s) used a model with no published "
            f"price — this total is a floor, not a bill."
        )
    blocks.extend(
        [
            "",
            "By team",
            table_of(
                [_team_row(line) for line in report.by_team],
                _TEAM_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing was spent in this period",
            ).render(invocation.terminal),
            "",
            "By run",
            table_of(
                [_run_row(line) for line in report.by_run],
                _RUN_COLUMNS,
                terminal=invocation.terminal,
                empty="no runs in this period",
            ).render(invocation.terminal),
        ]
    )
    return "\n".join(blocks)


def _shown(moment: datetime | None) -> str:
    """Return an instant as a date a person reads, or nothing."""
    return moment.date().isoformat() if moment else ""


def cost(
    ctx: typer.Context,
    team: str = typer.Option("", "--team", help="Only this team's runs."),
    since: str = typer.Option("", "--since", help="ISO-8601 date the period starts."),
    until: str = typer.Option("", "--until", help="ISO-8601 date the period ends."),
    limit: int = typer.Option(
        DEFAULT_SPEND_RUN_LIMIT, "--limit", help="How many recent runs to reach back over."
    ),
) -> None:
    """Report what a period cost, per team and per run."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        # Parsed inside the body rather than above it, so a bad date reports
        # through the same exit-code contract as every other command failure
        # instead of escaping as an unhandled exception.
        starts = _moment(since, flag="--since")
        ends = _moment(until, flag="--until")
        report = await invocation.client().spend(
            team_node_id=team or invocation.team_node_id,
            since=starts,
            until=ends,
            limit=limit,
        )
        warnings = (
            (f"{report.total.unpriced_runs} run(s) had no published price; the total is a floor",)
            if not report.total.is_complete
            else ()
        )
        return Output(
            command="cost",
            data=report.to_record(),
            text=report_text(report, invocation),
            warnings=warnings,
        )

    raise typer.Exit(run_command(invocation, "cost", body))


__all__ = ["DEFAULT_SPEND_RUN_LIMIT", "cost", "report_text"]
