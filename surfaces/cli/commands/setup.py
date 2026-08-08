"""``ninjasre setup`` — the first fifteen minutes, and the answers afterwards.

FR-010 asks for the self-check from the CLI, the console and bring-up; FR-022
asks that a bring-up failure be reachable afterwards from the console *and* the
CLI. This is the CLI half of both, and of demo mode.

**Two of these need no deployment at all.** ``credential`` and ``diagnose`` read
host files, and that is the point: they are what an operator runs when the
deployment did not come up, or came up and scrolled the token away. A command
that needed a working database to tell you why the database is not working would
be a command nobody could use when it mattered.

**The rest compose the store from the configured URL.** Not from the gateway —
``surfaces`` and ``gateway`` may not import each other — and not from a second
composition root either: the store is one call, and everything above it is the
same ``platform.startup`` code the gateway's routes call. The factory is
injectable so the whole group is driven in a test against the in-memory store.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

import typer

from config.constants.first_run import SUPPORT_BUNDLE_FILENAME
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from platform.persistence.ports.transaction import PersistenceGateway
from platform.startup.bootstrap import credential_path, read_credential
from platform.startup.demo import DemoRefused, remove_demonstration, seed_demonstration
from platform.startup.diagnostics import last_failure, support_bundle
from platform.startup.selfcheck import SelfCheckReport, self_check
from surfaces.cli.errors import CliError, ConfigurationError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.output.tables import Column, Detail, bullet_list, table_of

app = typer.Typer(help="Bring-up, the self-check, and the demonstration deployment.")

#: How the store is reached when nothing supplies one. Replaced in a test, and
#: only in a test: a deployment has exactly one database and it is the
#: configured one.
StoreFactory = Callable[[], PersistenceGateway]

_FINDING_COLUMNS = (
    Column("Blocks", weight=1),
    Column("Check", weight=1),
    Column("Problem", weight=4),
    Column("Do", weight=4),
)


def _default_store() -> PersistenceGateway:
    """Return the store this deployment is configured with.

    Raises:
        ConfigurationError: no database is configured, which is a different
            problem from one that is configured and unreachable — and the
            self-check would otherwise report the second for the first.
    """
    from platform.persistence.postgres.gateway import PostgresPersistence

    url = os.environ.get(NINJASRE_DATABASE_URL_ENV, "").strip()
    if not url:
        raise ConfigurationError(
            f"{NINJASRE_DATABASE_URL_ENV} is not set, so there is no deployment to check",
            remedy=f"set {NINJASRE_DATABASE_URL_ENV} to this deployment's database",
        )
    return PostgresPersistence.from_url(url)


#: Swapped by a test. Module-level rather than a parameter on every command,
#: because typer owns the signatures and threading a factory through six of them
#: would put a test seam in the operator's ``--help``.
store_factory: StoreFactory = _default_store


def _report_text(report: SelfCheckReport, invocation: Invocation) -> str:
    """Return the self-check as a person reads it."""
    if not report.findings:
        return (
            f"{invocation.terminal.glyph('ok')} nothing to report — "
            f"{len(report.passed)} checks, all clear"
        )
    rows = [
        {
            "blocks": finding.blocks,
            "check": finding.check,
            "problem": finding.problem,
            "do": finding.action,
        }
        for finding in report.ordered()
    ]
    return "\n".join(
        [
            f"{invocation.terminal.glyph('failed')} {len(report.findings)} problem(s), "
            f"most blocking first",
            "",
            table_of(
                rows,
                _FINDING_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing was checked, which is itself a problem",
            ).render(invocation.terminal),
        ]
    )


@app.command("self-check")
def check(ctx: typer.Context) -> None:
    """Report every problem this deployment has, in one pass, with what to do."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        store = store_factory()
        report = await self_check(store)
        return Output(
            command="setup.self-check",
            data=report.to_record(),
            text=_report_text(report, invocation),
            code=0 if report.ok else 1,
        )

    raise typer.Exit(run_command(invocation, "setup.self-check", body))


@app.command("credential")
def credential(ctx: typer.Context) -> None:
    """Print the bootstrap credential again, without restarting anything."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = read_credential()
        if found is None:
            raise CliError(
                f"there is no bootstrap credential at {credential_path()}",
                remedy=(
                    "it has already been exchanged for a durable one, or this deployment "
                    "has not been brought up on this host"
                ),
            )
        return Output(
            command="setup.credential",
            # The secret is in the payload because printing it is the whole
            # purpose of the command. It reaches no log on the way (FR-004).
            data=found.to_record(),
            text=Detail(
                title="bootstrap credential",
                pairs=(
                    ("Credential", found.secret),
                    ("Expires", found.expires_at.isoformat()),
                    ("Organisation", found.organisation_id),
                ),
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "setup.credential", body))


@app.command("diagnose")
def diagnose(ctx: typer.Context) -> None:
    """Show the last bring-up failure this host recorded, and what to do about it."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        failure = last_failure()
        if failure is None:
            return Output(
                command="setup.diagnose",
                data={"failure": None},
                text=f"{invocation.terminal.glyph('ok')} this deployment recorded no "
                f"bring-up failure",
            )
        return Output(
            command="setup.diagnose",
            # One shape whether or not there was a failure. A payload that is
            # sometimes a record and sometimes a null is two schemas, and a
            # script reading it has to branch on the shape before it can branch
            # on the answer.
            data={"failure": failure.to_record()},
            text=failure.summary(),
            code=1,
        )

    raise typer.Exit(run_command(invocation, "setup.diagnose", body))


@app.command("bundle")
def bundle(
    ctx: typer.Context,
    out: Path = typer.Option(
        Path(SUPPORT_BUNDLE_FILENAME), "--out", help="Where to write the bundle."
    ),
) -> None:
    """Write a support bundle: versions, configuration, logs, self-check, schema.

    Written locally and never transmitted. What happens to it afterwards is the
    operator's decision, which is why this command's output is a path rather
    than a confirmation that something was sent (Article X).
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        store = store_factory()
        health = await store.health()
        report = await self_check(store)
        written = support_bundle(
            environ=dict(os.environ),
            self_check=report,
            logs=(),
            schema_revision=(
                (health.migrations.applied_revision or "") if health.migrations else ""
            ),
        ).write(out)
        return Output(
            command="setup.bundle",
            data={"path": str(written)},
            text="\n".join(
                [
                    f"{invocation.terminal.glyph('ok')} wrote {written}",
                    "",
                    bullet_list(
                        [
                            "Nothing was transmitted.",
                            "Every documented secret is redacted; read it before sharing it.",
                        ],
                        terminal=invocation.terminal,
                    ),
                ]
            ),
        )

    raise typer.Exit(run_command(invocation, "setup.bundle", body))


# Flat rather than a ``demo`` sub-group. The published-schema contract names a
# command by its leaf under one group, so a second level of nesting would give
# both of these the same name and neither a schema of its own.
@app.command("load-demo")
def load_demo(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Seed even over data that is not a demonstration."
    ),
) -> None:
    """Populate this deployment with the demonstration estate, runs and incidents."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        store = store_factory()
        try:
            report = await seed_demonstration(store, force=force)
        except DemoRefused as refusal:
            raise CliError(
                str(refusal), remedy="pass --force if you really mean to mix the two"
            ) from refusal
        return Output(
            command="setup.load-demo",
            data=report.to_record(),
            text=f"{invocation.terminal.glyph('ok')} {report.summary()}",
        )

    raise typer.Exit(run_command(invocation, "setup.load-demo", body))


@app.command("remove-demo")
def remove_demo(ctx: typer.Context) -> None:
    """Remove the demonstration deployment entirely, in one action."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        store = store_factory()
        report = await remove_demonstration(store)
        return Output(
            command="setup.remove-demo",
            data=report.to_record(),
            text=f"{invocation.terminal.glyph('ok')} {report.summary()}",
        )

    raise typer.Exit(run_command(invocation, "setup.remove-demo", body))


def run_self_check_now(store: PersistenceGateway) -> SelfCheckReport:
    """Run the self-check synchronously, for a caller with no event loop.

    ``deploy/ops/preflight.py`` is that caller: it is a script an operator runs
    before starting anything, and giving it its own ``asyncio.run`` here keeps
    the third checker this feature was asked not to write from appearing there.
    """
    return asyncio.run(self_check(store))


__all__ = ["app", "run_self_check_now", "store_factory"]
