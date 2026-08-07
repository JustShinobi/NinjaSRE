"""``ninjasre onboard`` — nothing configured to something that works.

The command is thin on purpose: the flow lives in ``wizard/flow.py`` so it can
be run by a test, by the REPL's first-run path, and by an unattended install
without any of them going through a typer callback.
"""

from __future__ import annotations

import typer

from surfaces.cli.errors import ConfigurationError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, bullet_list, table_of
from surfaces.cli.wizard.flow import onboard as run_flow
from surfaces.cli.wizard.prompts import TyperPrompter

_INTEGRATION_COLUMNS = (
    Column("Integration", weight=2),
    Column("Configured", weight=1),
    Column("Healthy", weight=1),
    Column("Detail", weight=4),
)


def onboard(
    ctx: typer.Context,
    provider: str = typer.Option(
        "", "--provider", help="Skip the provider question and use this one."
    ),
    integration: list[str] = typer.Option(
        None, "--integration", help="Set this integration up. Repeatable."
    ),
) -> None:
    """Configure a provider, its credential, and any integrations, then verify."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        outcome = await run_flow(
            invocation.client(),
            TyperPrompter(),
            provider_id=provider,
            integrations=tuple(integration or ()),
        )
        if not outcome.verified:
            raise ConfigurationError(
                f"onboarding finished without a working provider: {outcome.detail}",
                remedy="run 'ninjasre doctor' to see what is missing",
            )

        blocks = [
            Detail(
                title=f"{invocation.terminal.glyph('ok')} configured",
                pairs=(
                    ("Provider", outcome.provider_id),
                    ("Model", outcome.model_id),
                    ("Verified", "yes"),
                ),
            ).render(invocation.terminal),
            "",
            table_of(
                records_of(outcome.integrations),
                _INTEGRATION_COLUMNS,
                terminal=invocation.terminal,
                title="Integrations",
                empty="none — add one with 'ninjasre integrations setup <name>'",
            ).render(invocation.terminal),
            "",
            "What happened",
            bullet_list(outcome.steps, terminal=invocation.terminal),
            "",
            "Try it: ninjasre investigate 'checkout latency doubled after the last deploy'",
        ]
        return Output(
            command="onboard",
            data=outcome.to_record(),
            text="\n".join(blocks),
        )

    raise typer.Exit(run_command(invocation, "onboard", body))


__all__ = ["onboard"]
