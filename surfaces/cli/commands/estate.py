"""``ninjasre estate`` — what the deployment is responsible for, and how it is doing.

Four commands. Listing what is out there, summarising it, opening one resource,
and the two halves of a maintenance window.

The health column shows the *reported* state — absence, maintenance and
freshness already applied by the deployment — because a CLI that applied
freshness itself would be a second copy of a rule that has to have exactly one,
and the two copies would disagree the first time somebody changed an interval.
``estate show`` prints the stored state beside it, which is what an operator
looking at ``stale`` wants next.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer

from surfaces.cli.client import EstateFilter
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(
    help="The estate: what is out there, and how each of it is doing.",
    no_args_is_help=True,
)

_RESOURCE_COLUMNS = (
    Column("Resource id", weight=2),
    Column("Kind", weight=1),
    Column("Name", weight=3),
    Column("Health", weight=1),
    Column("Source", weight=1),
    Column("Last seen at", weight=2),
)

_CHILD_COLUMNS = (
    Column("Resource id", weight=2),
    Column("Name", weight=3),
    Column("Health", weight=1),
)

_TRANSITION_COLUMNS = (
    Column("Occurred at", weight=2),
    Column("State", weight=1),
    Column("Previous state", weight=1),
    Column("Rule", weight=2),
)


def _rows(resources: object) -> list[dict[str, object]]:
    """Return the records a table renders, in the column order above."""
    return [
        {
            "resource_id": record["resource_id"],
            "kind": record["kind"],
            "display_name": record["display_name"],
            "health": record["health"],
            "source": record["source"],
            "last_seen_at": record["last_seen_at"],
        }
        for record in records_of(resources)  # type: ignore[arg-type]
    ]


@app.command("list")
def list_estate(
    ctx: typer.Context,
    kind: list[str] = typer.Option([], "--kind", help="Only resources of this kind."),
    health: list[str] = typer.Option([], "--health", help="Only resources in this state."),
    source: list[str] = typer.Option([], "--source", help="Only this integration's resources."),
    label: list[str] = typer.Option([], "--label", help="Only resources carrying this label."),
    parent: str = typer.Option("", "--parent", help="Only children of this resource."),
    team: str = typer.Option("", "--team", help="Only this team's resources."),
    gone: bool = typer.Option(False, "--gone", help="Include resources that are no longer there."),
    limit: int = typer.Option(100, "--limit", help="How many to return."),
) -> None:
    """List the estate."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_estate(
            EstateFilter(
                kinds=tuple(kind),
                health=tuple(health),
                sources=tuple(source),
                labels=tuple(label),
                team_node_id=team or invocation.team_node_id,
                parent_id=parent,
                include_absent=gone,
                limit=limit,
            )
        )
        return Output(
            command="estate.list",
            data={"resources": records_of(found)},
            text=table_of(
                _rows(found),
                _RESOURCE_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing has been discovered yet",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "estate.list", body))


@app.command("summary")
def estate_summary(ctx: typer.Context) -> None:
    """Summarise the estate: how much of it there is, and how much is a problem."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        summary = await invocation.client().estate_summary()
        by_kind = ", ".join(f"{name} {count}" for name, count in sorted(summary.by_kind.items()))
        text = Detail(
            title=f"{summary.total} resources",
            pairs=(
                ("Problems", str(summary.problems)),
                ("In maintenance", str(summary.maintenance)),
                ("Gone", str(summary.absent)),
                ("By kind", by_kind or "nothing discovered"),
                (
                    "Captured at",
                    summary.captured_at.isoformat() if summary.captured_at else "unknown",
                ),
            ),
        ).render(invocation.terminal)
        return Output(command="estate.summary", data=summary.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "estate.summary", body))


@app.command("show")
def show_resource(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="The resource to open."),
) -> None:
    """Show one resource: its state, why it is in it, and what has happened to it."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        detail = await invocation.client().show_resource(resource_id)
        resource = detail.resource
        head = Detail(
            title=f"{resource.display_name or resource.resource_id} ({resource.kind})",
            pairs=(
                ("Health", resource.health),
                ("Last derived", resource.stored_health),
                ("Why", detail.explanation or resource.explanation),
                ("Rule", detail.rule),
                ("Provider said", detail.raw_status or "nothing"),
                ("Sources", ", ".join(resource.sources) or resource.source),
                ("Rollup rule", detail.rollup_rule),
            ),
        ).render(invocation.terminal)

        sections = [head]
        if detail.children:
            sections.append(
                table_of(
                    [
                        {
                            "resource_id": child.resource_id,
                            "display_name": child.display_name,
                            "health": child.health,
                        }
                        for child in detail.children
                    ],
                    _CHILD_COLUMNS,
                    terminal=invocation.terminal,
                    empty="",
                ).render(invocation.terminal)
            )
        sections.append(
            table_of(
                records_of(detail.transitions),
                _TRANSITION_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing has changed since it was discovered",
            ).render(invocation.terminal)
        )

        return Output(
            command="estate.show",
            data=detail.to_record(),
            text="\n\n".join(section for section in sections if section),
        )

    raise typer.Exit(run_command(invocation, "estate.show", body))


@app.command("maintain")
def maintain_resource(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="The resource to suppress."),
    reason: str = typer.Option(..., "--reason", help="Why. Required, and stored."),
    hours: float = typer.Option(2.0, "--hours", help="How long the window lasts."),
) -> None:
    """Suppress a resource from the problem count while somebody works on it."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        until = datetime.now(UTC) + timedelta(hours=hours)
        updated = await invocation.client().set_maintenance(resource_id, until=until, reason=reason)
        text = Detail(
            title=f"{invocation.terminal.glyph('ok')} {updated.resource_id}",
            pairs=(
                ("Health", updated.health),
                ("Until", until.isoformat()),
                ("Reason", reason),
            ),
        ).render(invocation.terminal)
        return Output(command="estate.maintain", data=updated.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "estate.maintain", body))


@app.command("release")
def release_resource(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="The resource to stop suppressing."),
) -> None:
    """End a resource's maintenance window now."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        updated = await invocation.client().clear_maintenance(resource_id)
        return Output(
            command="estate.release",
            data=updated.to_record(),
            text=(
                f"{invocation.terminal.glyph('ok')} {updated.resource_id} "
                f"is back in the estate as {updated.health}"
            ),
        )

    raise typer.Exit(run_command(invocation, "estate.release", body))


__all__ = ["app"]
