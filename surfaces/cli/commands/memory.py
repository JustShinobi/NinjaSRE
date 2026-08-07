"""``ninjasre memory`` — what the platform has learned, exposed rather than implied.

Article VII: a learning mechanism nobody can inspect is a claim. ``stats``
reports the switches too, so "is the corpus being read at all" is a question an
operator answers here rather than by reading configuration.
"""

from __future__ import annotations

import typer

from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(help="Episodic memory: search the corpus and report on it.", no_args_is_help=True)

_COLUMNS = (
    Column("Episode id", weight=1),
    Column("Score", weight=1),
    Column("Occurred at", weight=2),
    Column("Title", weight=4),
    Column("Components", weight=3),
)


@app.command("search")
def search_memory(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="What to look for."),
    limit: int = typer.Option(10, "--limit", "-n", help="How many episodes to return."),
) -> None:
    """Search past investigations."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        hits = await invocation.client().search_memory(query, limit=limit)
        return Output(
            command="memory.search",
            data={"query": query, "hits": records_of(hits)},
            text=table_of(
                records_of(hits),
                _COLUMNS,
                terminal=invocation.terminal,
                title=f"Episodes matching {query!r}",
                empty="nothing in the corpus matches",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "memory.search", body))


@app.command("stats")
def memory_stats(ctx: typer.Context) -> None:
    """Report what the episodic corpus holds, and whether it is in use."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        stats = await invocation.client().memory_stats()
        warnings: list[str] = []
        if not stats.read_enabled:
            warnings.append("recall is switched off: no investigation is consulting the corpus")
        if not stats.write_enabled:
            warnings.append("extraction is switched off: no investigation is adding to the corpus")

        text = Detail(
            title="Episodic memory",
            pairs=(
                ("Episodes", str(stats.episodes)),
                ("Components", str(stats.components)),
                ("Mean effectiveness", f"{stats.mean_effectiveness:.3f}"),
                ("Oldest", stats.oldest_at.isoformat() if stats.oldest_at else "—"),
                ("Newest", stats.newest_at.isoformat() if stats.newest_at else "—"),
                ("Recall", "on" if stats.read_enabled else "off"),
                ("Extraction", "on" if stats.write_enabled else "off"),
            ),
        ).render(invocation.terminal)
        return Output(
            command="memory.stats",
            data=stats.to_record(),
            text=text,
            warnings=tuple(warnings),
        )

    raise typer.Exit(run_command(invocation, "memory.stats", body))


__all__ = ["app"]
