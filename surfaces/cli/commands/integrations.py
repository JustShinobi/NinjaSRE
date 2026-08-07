"""``ninjasre integrations`` — what the platform can look at, and whether it can.

``setup`` prompts. That is the whole of the credential rule at this surface: one
entered as a command argument is in the shell history before the process starts,
and there is no flag here that would accept one.
"""

from __future__ import annotations

import typer

from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, bullet_list, table_of
from surfaces.cli.wizard.integrations import setup as setup_integration
from surfaces.cli.wizard.prompts import TyperPrompter

app = typer.Typer(
    help="Vendor integrations: list them, set one up, verify one.", no_args_is_help=True
)

_COLUMNS = (
    Column("Integration", weight=2),
    Column("Configured", weight=1),
    Column("Healthy", weight=1),
    Column("Credential state", weight=2),
    Column("Detail", weight=4),
)


@app.command("list")
def list_integrations(ctx: typer.Context) -> None:
    """List every known integration and its current state."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        integrations = await invocation.client().list_integrations()
        return Output(
            command="integrations.list",
            data={"integrations": records_of(integrations)},
            text=table_of(
                records_of(integrations),
                _COLUMNS,
                terminal=invocation.terminal,
                empty="nothing is integrated yet — run 'ninjasre integrations setup <name>'",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "integrations.list", body))


@app.command("setup")
def setup(
    ctx: typer.Context,
    integration: str = typer.Argument(..., help="The integration to configure."),
) -> None:
    """Configure one integration.

    Prompts for whatever its credential schema declares and writes the result
    to the vault. Nothing is echoed, nothing is stored in configuration, and
    there is deliberately no way to pass a credential on the command line.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        outcome = await setup_integration(invocation.client(), integration, TyperPrompter())
        status = outcome.status
        glyph = invocation.terminal.glyph("ok" if outcome.usable else "warning")
        blocks = [
            Detail(
                title=f"{glyph} {status.integration}",
                pairs=(
                    ("Configured", "yes" if status.configured else "no"),
                    ("Healthy", "yes" if status.healthy else "no"),
                    ("Credential", status.credential_state),
                    ("Detail", status.detail),
                ),
            ).render(invocation.terminal)
        ]
        if outcome.entered:
            blocks.extend(
                ("", "Fields entered", bullet_list(outcome.entered, terminal=invocation.terminal))
            )
        if outcome.skipped:
            blocks.extend(
                ("", "Fields skipped", bullet_list(outcome.skipped, terminal=invocation.terminal))
            )
        return Output(
            command="integrations.setup",
            data=status.to_record(),
            text="\n".join(blocks),
        )

    raise typer.Exit(run_command(invocation, "integrations.setup", body))


@app.command("verify")
def verify(
    ctx: typer.Context,
    integration: str = typer.Argument(..., help="The integration to check."),
) -> None:
    """Check one integration's credential and connectivity."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        status = await invocation.client().verify_integration(integration)
        glyph = invocation.terminal.glyph("ok" if status.healthy else "failed")
        return Output(
            command="integrations.verify",
            data=status.to_record(),
            text=Detail(
                title=f"{glyph} {status.integration}",
                pairs=(
                    ("Configured", "yes" if status.configured else "no"),
                    ("Healthy", "yes" if status.healthy else "no"),
                    ("Credential", status.credential_state),
                    ("Detail", status.detail),
                ),
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "integrations.verify", body))


__all__ = ["app"]
