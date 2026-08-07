"""``ninjasre schedule`` — investigations that run without anybody starting them.

A scheduled run is an ordinary run: same records, same trace, same approvals,
differing only in its trigger. Nothing here is an autonomy bypass, and the
listing shows the same run identifiers ``runs list`` does for exactly that
reason.
"""

from __future__ import annotations

import typer

from surfaces.cli.client import ScheduleRequest
from surfaces.cli.errors import NotFoundError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(help="Recurring investigations: list, add, remove.", no_args_is_help=True)

_COLUMNS = (
    Column("Job id", weight=1),
    Column("Cron", weight=2),
    Column("Timezone", weight=1),
    Column("Enabled", weight=1),
    Column("Next fire at", weight=2),
    Column("Objective", weight=5),
)


@app.command("list")
def list_schedules(
    ctx: typer.Context,
    team: str = typer.Option("", "--team", help="Only this team's schedules."),
) -> None:
    """List the scheduled investigations."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        schedules = await invocation.client().list_schedules(
            team_node_id=team or invocation.team_node_id
        )
        return Output(
            command="schedule.list",
            data={"schedules": records_of(schedules)},
            text=table_of(
                records_of(schedules),
                _COLUMNS,
                terminal=invocation.terminal,
                empty="nothing is scheduled",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "schedule.list", body))


@app.command("add")
def add_schedule(
    ctx: typer.Context,
    objective: str = typer.Argument(..., help="What the scheduled run investigates."),
    cron: str = typer.Option(..., "--cron", help="A five-field cron expression."),
    timezone: str = typer.Option("UTC", "--timezone", help="The zone the cron is read in."),
    job_id: str = typer.Option("", "--id", help="An identifier. Generated when omitted."),
    team: str = typer.Option("", "--team", help="The team it runs as."),
) -> None:
    """Schedule a recurring investigation."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        created = await invocation.client().add_schedule(
            ScheduleRequest(
                objective=objective,
                cron=cron,
                timezone=timezone,
                team_node_id=team or invocation.team_node_id,
                job_id=job_id,
            )
        )
        text = Detail(
            title=f"{invocation.terminal.glyph('ok')} {created.job_id}",
            pairs=(
                ("Objective", created.objective),
                ("Cron", created.cron),
                ("Timezone", created.timezone),
                ("Team", created.team_node_id),
                (
                    "Next fire at",
                    created.next_fire_at.isoformat() if created.next_fire_at else "unknown",
                ),
            ),
        ).render(invocation.terminal)
        return Output(command="schedule.add", data=created.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "schedule.add", body))


@app.command("remove")
def remove_schedule(
    ctx: typer.Context, job_id: str = typer.Argument(..., help="The schedule to remove.")
) -> None:
    """Remove a scheduled investigation."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        removed = await invocation.client().remove_schedule(job_id)
        if not removed:
            raise NotFoundError(
                f"no schedule named {job_id!r}",
                remedy="list what there is with 'ninjasre schedule list'",
            )
        return Output(
            command="schedule.remove",
            data={"job_id": job_id, "removed": removed},
            text=f"{invocation.terminal.glyph('ok')} removed {job_id}",
        )

    raise typer.Exit(run_command(invocation, "schedule.remove", body))


__all__ = ["app"]
