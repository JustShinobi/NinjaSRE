"""``ninjasre runs`` — what has been investigated, and what one investigation did.

``replay`` is the one that matters constitutionally. It rebuilds a past run from
its recorded events and nothing else, so what it shows is exactly what the trace
can reproduce — and anything an operator can see here is something the platform
can prove happened.
"""

from __future__ import annotations

import typer

from config.constants.runs import DEFAULT_RUN_HISTORY_PAGE_SIZE
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import RunDetail, RunReplay, RunSummary, records_of
from surfaces.cli.output.tables import Column, Detail, TableView, bullet_list, table_of

app = typer.Typer(help="Investigation history: list, show, and replay runs.", no_args_is_help=True)

_RUN_COLUMNS = (
    Column("Run id", weight=1),
    Column("Status", weight=1),
    Column("Trigger", weight=1),
    Column("Started at", weight=2),
    Column("Objective", weight=6),
)

_STAGE_COLUMNS = (
    Column("Stage", weight=1),
    Column("Started at", weight=2),
    Column("Ended at", weight=2),
    Column("Failed", weight=1),
)


def _runs_table(runs: tuple[RunSummary, ...], invocation: Invocation) -> TableView:
    """Return the listing table for ``runs``."""
    return table_of(
        records_of(runs),
        _RUN_COLUMNS,
        terminal=invocation.terminal,
        empty="no runs yet — start one with 'ninjasre investigate'",
    )


def _detail_text(detail: RunDetail, invocation: Invocation) -> str:
    """Return the human rendering of one run in full."""
    run = detail.run
    head = Detail(
        title=run.run_id,
        pairs=(
            ("Status", run.status),
            ("Trigger", run.trigger),
            ("Objective", run.objective),
            ("Team", run.team_node_id),
            ("Principal", run.principal_id),
            ("Evidence", str(len(detail.evidence_ids))),
            ("Tokens", str(detail.cost.total_tokens)),
            ("Cost", f"{detail.cost.cost:.4f}"),
        ),
    ).render(invocation.terminal)

    stages = table_of(
        records_of(detail.stages),
        _STAGE_COLUMNS,
        terminal=invocation.terminal,
        title="Stages",
        empty="no stage ran",
    ).render(invocation.terminal)

    blocks = [head, "", stages]
    if detail.result:
        blocks.extend(("", "Result", "", detail.result))
    if detail.errors:
        blocks.extend(("", "Errors", "", bullet_list(detail.errors, terminal=invocation.terminal)))
    return "\n".join(blocks)


def _replay_text(replay: RunReplay, invocation: Invocation) -> str:
    """Return the human rendering of a replayed run."""
    lines = [
        f"{replay.run_id}: {len(replay.events)} recorded events",
        "",
    ]
    arrow = invocation.terminal.glyph("arrow")
    for event in replay.events:
        sequence = event.get("sequence", "")
        kind = event.get("kind", "")
        text = str(event.get("text", "") or event.get("capability", ""))
        lines.append(f"{sequence:>5}  {kind:<18} {arrow} {text}")

    if replay.view is not None:
        lines.extend(("", _detail_text(replay.view, invocation)))
    return "\n".join(lines)


@app.command("list")
def list_runs(
    ctx: typer.Context,
    limit: int = typer.Option(
        DEFAULT_RUN_HISTORY_PAGE_SIZE, "--limit", "-n", help="How many runs to show."
    ),
    team: str = typer.Option("", "--team", help="Only this team's runs."),
) -> None:
    """List recent investigations, newest first."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        client = invocation.client()
        scope = team or invocation.team_node_id
        runs = await client.list_runs(team_node_id=scope, limit=limit)
        cost = await client.cost_of_runs(team_node_id=scope, limit=limit)
        return Output(
            command="runs.list",
            data={"runs": records_of(runs), "cost": cost.to_record()},
            text=_runs_table(runs, invocation).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "runs.list", body))


@app.command("show")
def show_run(
    ctx: typer.Context, run_id: str = typer.Argument(..., help="The run to show.")
) -> None:
    """Show one investigation in full."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        detail = await invocation.client().show_run(run_id)
        return Output(
            command="runs.show",
            data=detail.to_record(),
            text=_detail_text(detail, invocation),
        )

    raise typer.Exit(run_command(invocation, "runs.show", body))


@app.command("replay")
def replay_run(
    ctx: typer.Context, run_id: str = typer.Argument(..., help="The run to replay.")
) -> None:
    """Rebuild one investigation from its recorded events alone."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        replay = await invocation.client().replay_run(run_id)
        return Output(
            command="runs.replay",
            data=replay.to_record(),
            text=_replay_text(replay, invocation),
        )

    raise typer.Exit(run_command(invocation, "runs.replay", body))


__all__ = ["app"]
