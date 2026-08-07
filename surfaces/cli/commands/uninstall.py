"""``ninjasre uninstall`` — take everything back off the machine.

All local data, on confirmation. Both halves of that are load-bearing.

**All of it.** Configuration, cache, data, and state, which on a POSIX host are
four different directories under four different XDG roots. An uninstall that
left the state directory behind would leave a REPL history containing whatever
somebody typed during an incident.

**On confirmation.** The list of paths is shown *first*, then the question is
asked. An operator who is about to lose their configuration is entitled to see
what that means before saying yes, and a ``--yes`` flag exists for the
unattended case rather than as the default.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

import typer

from config.constants.paths import cache_dir, config_dir, data_dir, home_dir, state_dir
from platform.observability.logging import get_logger
from surfaces.cli.errors import CliError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import LifecycleOutcome
from surfaces.cli.output.tables import bullet_list

logger = get_logger(__name__)


def local_data_paths() -> tuple[Path, ...]:
    """Return every directory this installation may have written to.

    All four roots plus the single-directory override, de-duplicated: a
    deployment using ``NINJASRE_HOME_DIR`` has all four nested inside one, and
    listing the same tree five times would make the confirmation prompt lie
    about how much there is.
    """
    candidates = (home_dir(), config_dir(), cache_dir(), data_dir(), state_dir())
    seen: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved not in seen and not any(
            resolved.is_relative_to(kept) for kept in seen if kept != resolved
        ):
            seen.append(resolved)
    return tuple(seen)


def existing_paths(paths: Sequence[Path] | None = None) -> tuple[Path, ...]:
    """Return the paths that are actually on disk."""
    return tuple(
        path for path in (paths if paths is not None else local_data_paths()) if path.exists()
    )


def remove(paths: Sequence[Path]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Delete ``paths`` and return what went and what would not.

    A path that could not be removed is reported rather than raised on, and the
    rest still go. Stopping at the first permission error would leave an
    uninstall half-done and no record of which half.
    """
    removed: list[str] = []
    failed: list[str] = []
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as failure:
            failed.append(f"{path}: {failure}")
            continue
        removed.append(str(path))
        logger.info("cli.uninstalled_path", path=str(path))
    return tuple(removed), tuple(failed)


def uninstall(
    ctx: typer.Context,
    assume_yes: bool = typer.Option(
        False, "--yes", "-y", help="Do not ask. For an unattended teardown."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List what would go without removing anything."
    ),
) -> None:
    """Remove all local NinjaSRE data from this machine."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        present = existing_paths()
        if not present:
            return Output(
                command="uninstall",
                data=LifecycleOutcome(
                    action="uninstall", changed=False, detail="nothing to remove"
                ).to_record(),
                text="nothing to remove: no local NinjaSRE data on this machine",
            )

        listing = bullet_list([str(path) for path in present], terminal=invocation.terminal)
        if dry_run:
            outcome = LifecycleOutcome(
                action="uninstall",
                changed=False,
                removed=tuple(str(path) for path in present),
                detail="dry run: nothing was removed",
            )
            return Output(
                command="uninstall",
                data=outcome.to_record(),
                text=f"These would be removed:\n{listing}",
            )

        if not assume_yes:
            invocation.write(f"These will be removed:\n{listing}")
            if not typer.confirm("Remove all of it?", default=False):
                raise CliError(
                    "nothing was removed", remedy="rerun with --yes to skip the question"
                )

        removed, failed = remove(present)
        outcome = LifecycleOutcome(
            action="uninstall",
            changed=bool(removed),
            removed=removed,
            detail="; ".join(failed) if failed else "all local data removed",
        )
        text = f"{invocation.terminal.glyph('ok')} removed:\n" + bullet_list(
            removed, terminal=invocation.terminal, empty="nothing"
        )
        return Output(
            command="uninstall",
            data=outcome.to_record(),
            text=text,
            warnings=failed,
        )

    raise typer.Exit(run_command(invocation, "uninstall", body))


__all__ = ["existing_paths", "local_data_paths", "remove", "uninstall"]
