"""``ninjasre providers`` — every model provider, treated the same way.

All nine are listed whether or not they are configured, and the local one is
listed alongside the rest rather than under a heading. Article VI is a property
of the listing as much as of the adapter layer: a deployment that runs entirely
on operator-controlled infrastructure has to look like an ordinary choice here,
not like the option somebody had to go and find.
"""

from __future__ import annotations

import typer

from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(help="Model providers: list them, verify one.", no_args_is_help=True)

_COLUMNS = (
    Column("Provider id", weight=1),
    Column("Configured", weight=1),
    Column("Local", weight=1),
    Column("Verified", weight=1),
    Column("Model id", weight=2),
    Column("Detail", weight=4),
)


@app.command("list")
def list_providers(ctx: typer.Context) -> None:
    """List every supported provider and this deployment's state for it."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        providers = await invocation.client().list_providers()
        configured = [status for status in providers if status.configured]
        warnings = () if configured else ("no provider is configured — run 'ninjasre onboard'",)
        return Output(
            command="providers.list",
            data={"providers": records_of(providers)},
            text=table_of(
                records_of(providers),
                _COLUMNS,
                terminal=invocation.terminal,
                empty="no providers are registered, which should not be possible",
            ).render(invocation.terminal),
            warnings=warnings,
        )

    raise typer.Exit(run_command(invocation, "providers.list", body))


@app.command("verify")
def verify_provider(
    ctx: typer.Context,
    provider_id: str = typer.Argument(..., help="The provider to check."),
) -> None:
    """Check one provider end to end.

    Costs tokens against the operator's own endpoint, because the things a
    recorded fixture cannot prove — authentication, a tool call, a structured
    output, a stream — are exactly the things this is for.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        status = await invocation.client().verify_provider(provider_id)
        glyph = invocation.terminal.glyph("ok" if status.verified else "failed")
        text = Detail(
            title=f"{glyph} {status.provider_id}",
            pairs=(
                ("Configured", "yes" if status.configured else "no"),
                ("Runs locally", "yes" if status.local else "no"),
                ("Verified", "yes" if status.verified else "no"),
                ("Model", status.model_id),
                ("Detail", status.detail),
            ),
        ).render(invocation.terminal)
        return Output(command="providers.verify", data=status.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "providers.verify", body))


__all__ = ["app"]
