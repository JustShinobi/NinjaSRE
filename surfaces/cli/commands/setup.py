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
import sys
from collections.abc import Callable
from pathlib import Path

import typer

from config.constants.first_run import LOCAL_SIGN_IN_OPENED_VIA_CLI, SUPPORT_BUNDLE_FILENAME
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.enrolment import enrol_local_administrator
from platform.identity.errors import LocalAdministratorNameTaken, LocalEnrolmentBlockedBySso
from platform.identity.tokens import TokenService
from platform.persistence.ports.transaction import PersistenceGateway
from platform.startup.bootstrap import credential_path, organisation_id, read_credential
from platform.startup.demo import DemoRefused, remove_demonstration, seed_demonstration
from platform.startup.diagnostics import last_failure, support_bundle
from platform.startup.selfcheck import SelfCheckReport, self_check
from surfaces.cli.errors import CliError, ConfigurationError, DeniedError, UnavailableError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.output.tables import Column, Detail, bullet_list, table_of
from surfaces.cli.wizard.prompts import Prompter, TyperPrompter

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


def _stdin_is_a_terminal() -> bool:
    return sys.stdin.isatty()


#: Swapped by a test, the same way ``store_factory`` is. The default asks the
#: only question that matters for a passphrase prompt: can this process hide
#: what is typed and read it back reliably.
interactive_input: Callable[[], bool] = _stdin_is_a_terminal

#: Swapped by a test to hand back a ``ScriptedPrompter`` instead of one that
#: reads a real terminal.
prompter_factory: Callable[[], Prompter] = TyperPrompter


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


@app.command("admin")
def admin(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="The administrator's sign-in name."),
    rotate: bool = typer.Option(
        False,
        "--rotate",
        help="Replace an existing administrator's passphrase instead of refusing.",
    ),
) -> None:
    """Create this deployment's administrator, or rotate one that already exists.

    The canonical way in on the first day, and the answer to the two
    questions that come after it: this same command, run again with a new
    name, creates a second administrator; run again with the same name and
    ``--rotate``, it replaces that administrator's passphrase and revokes
    whatever sessions were open with the old one.

    Asks for the passphrase twice, without echoing it. Never accepts one as
    an argument or reads one from the environment — a passphrase on the
    command line is a passphrase in the shell history and in the process
    table, and one read from the environment by this command's own choice is
    one more place an operator has to remember to unset it.
    """
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        if not interactive_input():
            raise CliError(
                "this command needs an interactive terminal to ask for a passphrase "
                "without echoing it",
                remedy=(
                    "run it with a real terminal attached to this deployment's app "
                    "container — for example 'docker compose exec -it app ninjasre "
                    "setup admin --name ...', or your deployment's equivalent — or "
                    "exchange the bootstrap credential printed at first start through "
                    "the console's sign-in form instead"
                ),
            )

        prompter = prompter_factory()
        password = prompter.secret(f"Passphrase for {name!r}")
        confirmation = prompter.secret("Confirm passphrase")
        if password != confirmation:
            raise CliError("the two passphrases did not match", remedy="run the command again")

        store = store_factory()
        health = await store.health()
        if not health.connected:
            raise UnavailableError(
                f"could not reach the database: {'; '.join(health.reasons)}",
                remedy=(f"check the database is up and {NINJASRE_DATABASE_URL_ENV} points at it"),
            )

        tokens = TokenService(gateway=store, recorder=AuditRecorder(gateway=store))
        try:
            enrolled = await enrol_local_administrator(
                store,
                tokens,
                org_id=organisation_id(),
                name=name,
                password=password,
                rotate=rotate,
                opened_via=LOCAL_SIGN_IN_OPENED_VIA_CLI,
                recorder=AuditRecorder(gateway=store),
            )
        except LocalAdministratorNameTaken as taken:
            raise CliError(
                str(taken), remedy="pass --rotate to replace that administrator's passphrase"
            ) from taken
        except LocalEnrolmentBlockedBySso as blocked:
            raise DeniedError(str(blocked)) from blocked

        verb = "rotated" if enrolled.rotated else "created"
        return Output(
            command="setup.admin",
            data={
                "name": enrolled.name,
                "rotated": enrolled.rotated,
                "opened": enrolled.opened,
            },
            text=(
                f"{invocation.terminal.glyph('ok')} {enrolled.name!r} {verb}. Sign in at the "
                f"console with that name and the passphrase you just entered."
            ),
        )

    raise typer.Exit(run_command(invocation, "setup.admin", body))


def run_self_check_now(store: PersistenceGateway) -> SelfCheckReport:
    """Run the self-check synchronously, for a caller with no event loop.

    ``deploy/ops/preflight.py`` is that caller: it is a script an operator runs
    before starting anything, and giving it its own ``asyncio.run`` here keeps
    the third checker this feature was asked not to write from appearing there.
    """
    return asyncio.run(self_check(store))


__all__ = ["app", "run_self_check_now", "store_factory"]
