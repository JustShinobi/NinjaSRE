"""``ninjasre update`` — check for a newer build, when the operator asks.

Nothing here runs on its own. Article X forbids a version check that transmits
off-host without being asked, so this is a command an operator types and never
a background task, a startup probe, or a nag. What it reports is what the
installer would install; installing it is the installer's job, because a
process that replaced its own binary mid-run is a class of failure nobody
wants to debug.
"""

from __future__ import annotations

from importlib import metadata

import typer

from config.constants.surfaces import CLI_COMMAND_NAME
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import LifecycleOutcome
from surfaces.cli.output.tables import Detail

DISTRIBUTION_NAME = "ninjasre"


def installed_version() -> str:
    """Return the version of the installed distribution, or the empty string."""
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        # Running from a source checkout without an install. Not an error, and
        # not something to invent a version for.
        return ""


def update(
    ctx: typer.Context,
    check_only: bool = typer.Option(
        False, "--check", help="Report what is available without printing install instructions."
    ),
) -> None:
    """Report the installed version and how to move to a newer one."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        current = installed_version()
        instruction = (
            ""
            if check_only
            else (
                f"Re-run the installer to update:\n"
                f"  curl -fsSL https://get.ninjasre.dev/install.sh | sh\n"
                f"or, if you installed with Homebrew:\n"
                f"  brew upgrade {CLI_COMMAND_NAME}"
            )
        )
        outcome = LifecycleOutcome(
            action="update",
            changed=False,
            from_version=current,
            to_version="",
            detail=(
                "this command reports; the installer installs. Nothing was "
                "transmitted and nothing was changed."
            ),
        )
        text = Detail(
            title=f"{CLI_COMMAND_NAME} {current or 'from a source checkout'}",
            pairs=(("Installed", current or "not installed as a distribution"),),
            sections=(("How to update", instruction),) if instruction else (),
        ).render(invocation.terminal)
        return Output(command="update", data=outcome.to_record(), text=text)

    raise typer.Exit(run_command(invocation, "update", body))


__all__ = ["installed_version", "update"]
