"""``ninjasre integrations`` — what the platform can look at, and whether it can.

``setup`` prompts. That is the whole of the credential rule at this surface: one
entered as a command argument is in the shell history before the process starts,
and there is no flag here that would accept one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import typer

from platform.observability.diagnostics import health_summary
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


@app.command("health")
def health(ctx: typer.Context) -> None:
    """Say in one line whether every configured integration is answering.

    The command an operator runs from a shell prompt or a cron entry rather
    than opening a dashboard for. "Not configured" is reported separately from
    "not working": one is a task and the other is an outage, and a deployment
    that reported sixty problems on its first day is one whose health output
    nobody reads by the second.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        integrations = await invocation.client().list_integrations()
        summary = health_summary(records_of(integrations))
        broken = [status for status in integrations if status.configured and not status.healthy]
        blocks = [
            f"{invocation.terminal.glyph('ok' if summary.all_healthy else 'failed')} "
            f"{summary.headline()}"
        ]
        if broken:
            blocks.extend(
                (
                    "",
                    bullet_list(
                        [
                            f"{status.integration}: {status.detail or status.credential_state}"
                            for status in broken
                        ],
                        terminal=invocation.terminal,
                    ),
                )
            )
        return Output(
            command="integrations.health",
            data=summary.to_record(),
            text="\n".join(blocks),
            warnings=tuple(f"{status.integration} is not answering" for status in broken),
        )

    raise typer.Exit(run_command(invocation, "integrations.health", body))


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


#: What the shallow verify cannot answer, said once. Printed when ``--report``
#: was asked for and the deployment has no way to reach the vendor.
_NO_DEEP_VERIFIER = (
    "this deployment cannot reach the vendor — no deep verifier is composed, so what is "
    "above is the credential's state and not the vendor's answer"
)


def _report_pairs(document: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    """Return the vendor's own answer as the lines a terminal prints.

    A signal source answers two questions a credential check cannot reach —
    whether it is holding anything, and whether its clock agrees with ours — and
    each is rendered only when it was asked. A vendor that is not a signal
    source has neither, and printing "clock: unknown" for it would invent a
    measurement nobody made.
    """
    if document is None:
        return (("Vendor report", _NO_DEEP_VERIFIER),)

    pairs: list[tuple[str, str]] = []
    window = document.get("data_window")
    if isinstance(window, Mapping):
        rows = window.get("rows", 0)
        minutes = window.get("window_minutes", 0)
        pairs.append(("Data", f"{rows} record(s) over the last {minutes}m — {window.get('probe')}"))
        if window.get("state") == "empty_window" and not window.get("usable", True):
            pairs.append(("Empty window", str(window.get("advice", ""))))

    clock = document.get("clock")
    if isinstance(clock, Mapping):
        offset = clock.get("offset_seconds")
        tolerance = clock.get("tolerance_seconds", 0.0)
        pairs.append(
            (
                "Clock",
                "not reported by this source"
                if offset is None
                else f"{float(offset):+.1f}s from this platform, tolerance {float(tolerance):.1f}s",
            )
        )

    degradations = document.get("degradations")
    if isinstance(degradations, list) and degradations:
        pairs.append(("Degraded", "; ".join(str(reason) for reason in degradations)))
    return tuple(pairs)


@app.command("verify")
def verify(
    ctx: typer.Context,
    integration: str = typer.Argument(..., help="The integration to check."),
    report: bool = typer.Option(
        False,
        "--report",
        help=(
            "Also ask the vendor itself: whether it is holding recent data, and whether "
            "its clock agrees with this platform's. Makes live calls."
        ),
    ),
) -> None:
    """Check one integration's credential and connectivity.

    ``--report`` is a separate flag rather than the default because it costs
    something. The check without it reads what this deployment stored; the check
    with it reaches the vendor, and a screen that made that call on every render
    would be spending an operator's rate limit to redraw a page.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        client = invocation.client()
        status = await client.verify_integration(integration)
        document = await client.verify_integration_report(integration) if report else None
        glyph = invocation.terminal.glyph("ok" if status.healthy else "failed")
        data: dict[str, Any] = dict(status.to_record())
        if report:
            data["report"] = dict(document) if document is not None else None
        return Output(
            command="integrations.verify",
            data=data,
            text=Detail(
                title=f"{glyph} {status.integration}",
                pairs=(
                    ("Configured", "yes" if status.configured else "no"),
                    ("Healthy", "yes" if status.healthy else "no"),
                    ("Credential", status.credential_state),
                    ("Detail", status.detail),
                    *(_report_pairs(document) if report else ()),
                ),
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "integrations.verify", body))


__all__ = ["app"]
