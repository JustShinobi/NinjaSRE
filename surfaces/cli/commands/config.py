"""``ninjasre config`` — what a team's configuration resolves to, and why.

Every value shown carries the node that supplied it. "Why is this team using
that model" is asked constantly on a deep tree, and a listing that answered it
only by omission is a listing that makes people walk the tree by hand.

``set`` refuses secrets rather than storing them. The configuration service
already rejects a secret-shaped value with a pointer to the vault; this surface
never gives it the chance, because a credential typed as a command argument is
in the shell history before anything downstream sees it.
"""

from __future__ import annotations

import typer

from surfaces.cli.errors import ApprovalRequiredError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(
    help="Configuration: show what resolves, change it, compare two teams.",
    no_args_is_help=True,
)

_ENTRY_COLUMNS = (
    Column("Path", weight=3),
    Column("Value", weight=4),
    Column("Source node id", weight=2),
)

_DELTA_COLUMNS = (
    Column("Path", weight=3),
    Column("Left", weight=3),
    Column("Right", weight=3),
)


@app.command("show")
def show_config(
    ctx: typer.Context,
    node: str = typer.Argument("", help="The node to resolve. Defaults to --team."),
) -> None:
    """Show one node's effective configuration, every value attributed."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        node_id = node or invocation.team_node_id
        view = await invocation.client().show_config(node_id)
        return Output(
            command="config.show",
            data=view.to_record(),
            text=table_of(
                records_of(view.entries),
                _ENTRY_COLUMNS,
                terminal=invocation.terminal,
                title=f"Effective configuration for {view.node_id}",
                empty="nothing is configured on this node",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "config.show", body))


@app.command("set")
def set_config(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Dotted path of the field to set."),
    value: str = typer.Argument(..., help="The new value. Never a credential."),
    node: str = typer.Option("", "--node", help="The node to write on. Defaults to --team."),
) -> None:
    """Set one configuration value.

    Credentials do not go here. Enter one with 'ninjasre integrations setup',
    which prompts for it and writes it to the vault without it ever appearing in
    an argument, a config file, or the shell history.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        node_id = node or invocation.team_node_id
        change = await invocation.client().set_config(node_id, path, value)
        if change.requires_approval and not change.applied:
            raise ApprovalRequiredError(
                f"changing {path} on {node_id} needs an approval",
                remedy=change.detail or "approve it in the console or with /approve",
            )
        glyph = invocation.terminal.glyph("ok" if change.applied else "warning")
        text = Detail(
            title=f"{glyph} {node_id}",
            pairs=(
                ("Path", change.path),
                ("Before", change.before),
                ("After", change.after),
                ("Applied", "yes" if change.applied else "no"),
                ("Detail", change.detail),
            ),
        ).render(invocation.terminal)
        return Output(command="config.set", data=change.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "config.set", body))


@app.command("diff")
def diff_config(
    ctx: typer.Context,
    left: str = typer.Argument(..., help="The node on the left."),
    right: str = typer.Argument(..., help="The node on the right."),
) -> None:
    """Compare two nodes' effective configuration."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        diff = await invocation.client().diff_config(left, right)
        return Output(
            command="config.diff",
            data=diff.to_record(),
            text=table_of(
                records_of(diff.deltas),
                _DELTA_COLUMNS,
                terminal=invocation.terminal,
                title=f"{diff.left_node_id} against {diff.right_node_id}",
                empty="the two resolve identically",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "config.diff", body))


__all__ = ["app"]
