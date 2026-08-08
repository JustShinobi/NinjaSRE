"""The ``ninjasre`` command: every subcommand, and the decisions taken before one runs.

The root callback resolves four things once — what the terminal can render,
whether the output is for a machine, which deployment to talk to, and which
team to act as — and hands them down as an ``Invocation``. Nothing below has a
branch on any of them, which is why ``--json`` works on every command rather
than on the ones somebody remembered.

With no subcommand and a TTY, this starts the REPL. Without a TTY it says so
and exits, rather than sitting on a closed stdin waiting for a line that will
never arrive — the failure mode that turns a CI job into a timeout.
"""

from __future__ import annotations

import os
import sys

import typer

from config.constants.surfaces import (
    CLI_COMMAND_NAME,
    EXIT_OK,
    NINJASRE_ENDPOINT_ENV,
    NINJASRE_OUTPUT_FORMAT_ENV,
    NO_COLOR_ENV,
    OUTPUT_FORMAT_JSON,
)
from surfaces.cli.client import endpoint_from
from surfaces.cli.commands import config as config_commands
from surfaces.cli.commands import estate as estate_commands
from surfaces.cli.commands import integrations as integration_commands
from surfaces.cli.commands import memory as memory_commands
from surfaces.cli.commands import providers as provider_commands
from surfaces.cli.commands import runs as run_commands
from surfaces.cli.commands import schedule as schedule_commands
from surfaces.cli.commands.cost import cost
from surfaces.cli.commands.doctor import doctor
from surfaces.cli.commands.investigate import investigate
from surfaces.cli.commands.onboard import onboard
from surfaces.cli.commands.uninstall import uninstall
from surfaces.cli.commands.update import installed_version, update
from surfaces.cli.errors import describe_exit_codes
from surfaces.cli.invocation import Invocation, ServicesFactory
from surfaces.cli.output.degradation import detect

app = typer.Typer(
    name=CLI_COMMAND_NAME,
    help=(
        "Investigate production incidents with evidence, not assertions.\n\n"
        "Run with no arguments in a terminal to start the interactive session."
    ),
    add_completion=True,
    no_args_is_help=False,
    rich_markup_mode=None,
)

app.add_typer(run_commands.app, name="runs")
app.add_typer(config_commands.app, name="config")
app.add_typer(schedule_commands.app, name="schedule")
app.add_typer(memory_commands.app, name="memory")
app.add_typer(estate_commands.app, name="estate")
app.add_typer(provider_commands.app, name="providers")
app.add_typer(integration_commands.app, name="integrations")

app.command("investigate")(investigate)
app.command("cost")(cost)
app.command("onboard")(onboard)
app.command("doctor")(doctor)
app.command("update")(update)
app.command("uninstall")(uninstall)


#: Set by a deployment's composition root to make the CLI able to run a platform
#: in this process. Left unset, every command needs ``--endpoint`` — which is
#: the honest failure for a CLI installed on a laptop with no database behind it.
LOCAL_SERVICES: ServicesFactory | None = None


def use_local_services(factory: ServicesFactory | None) -> None:
    """Register how to compose an in-process platform.

    A module-level registration rather than a constructor argument because the
    entry point in ``pyproject.toml`` calls ``main()`` with no arguments, and a
    deployment profile is the thing that knows how to build a platform.
    """
    global LOCAL_SERVICES
    LOCAL_SERVICES = factory


def _version_callback(requested: bool) -> None:
    """Print the installed version and stop, when ``--version`` was given."""
    if requested:
        typer.echo(installed_version() or "unknown (running from a source checkout)")
        raise typer.Exit(EXIT_OK)


def _exit_codes_callback(requested: bool) -> None:
    """Print the exit-code contract and stop, when ``--exit-codes`` was given."""
    if requested:
        typer.echo(describe_exit_codes())
        raise typer.Exit(EXIT_OK)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    as_json: bool = typer.Option(
        False, "--json", help="Emit the documented JSON shape instead of a table."
    ),
    no_colour: bool = typer.Option(False, "--no-color", help="Never use colour."),
    endpoint: str = typer.Option(
        "", "--endpoint", envvar=NINJASRE_ENDPOINT_ENV, help="A remote deployment to operate."
    ),
    token: str = typer.Option("", "--token", help="Bearer token for a remote deployment."),
    team: str = typer.Option("", "--team", help="The team node to act as."),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Print the version."
    ),
    exit_codes: bool = typer.Option(
        False,
        "--exit-codes",
        callback=_exit_codes_callback,
        is_eager=True,
        help="Print what each exit code means.",
    ),
) -> None:
    """Resolve everything a command needs, then either run it or start the REPL."""
    environ = dict(os.environ)
    if no_colour:
        # Set rather than branched on, so the terminal detection stays the one
        # place that decides what colour means — including for the REPL, which
        # inherits this environment rather than the flag.
        environ[NO_COLOR_ENV] = "1"

    terminal = detect(stream=sys.stdout, environ=environ)
    wants_json = as_json or environ.get(NINJASRE_OUTPUT_FORMAT_ENV, "") == OUTPUT_FORMAT_JSON

    ctx.obj = Invocation(
        terminal=terminal,
        as_json=wants_json,
        team_node_id=team,
        endpoint=endpoint_from(endpoint, token=token),
        services_factory=LOCAL_SERVICES,
    )

    if ctx.invoked_subcommand is not None:
        return

    # No subcommand. Imported here rather than at module scope because the REPL
    # pulls in prompt_toolkit, and ``ninjasre runs list`` should not pay for a
    # terminal library it never uses.
    from surfaces.repl.loop import start

    raise typer.Exit(start(ctx.obj))


__all__ = ["app", "main", "use_local_services"]
