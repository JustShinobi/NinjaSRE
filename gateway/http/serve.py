"""The process a container runs: boot sequence first, then the ASGI server.

``python -m gateway.http.serve`` rather than pointing an ASGI server at a
factory, for one reason that is easy to get wrong. Migrations, the extension
probe, and the credential check all open database connections, and asyncpg
binds a pooled connection to the event loop that created it. Running the boot
sequence with ``asyncio.run`` and then handing the same engine to a server that
starts a *second* loop produces a deployment that starts perfectly and fails on
its first query. So there is one loop, created here, and everything happens
inside it.

The order is ``platform.startup.sequence``'s, and the reasons are documented
there. What this module adds is the two things that sequence deliberately does
not know about: which backend is behind the ports, and how to serve HTTP.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping, Sequence

import uvicorn

from config.constants.deployment import NINJASRE_ADMIN_TOKEN_ENV
from config.constants.first_run import LOCAL_ADMIN_SETUP_COMMAND
from config.constants.surfaces import DEFAULT_API_HOST, DEFAULT_API_PORT
from core.llm.factory import publish_configured_bindings
from gateway.http.app import create_app
from gateway.http.asgi import Deployment, build_deployment
from platform.config_service.service import ConfigService
from platform.credentials.errors import VaultKeyMismatch
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope
from platform.persistence.ports.health import StoreHealth
from platform.startup.bootstrap import announcement, bring_up, credential_path, organisation_id
from platform.startup.diagnostics import forget_failure, record_failure
from platform.startup.errors import StartupError
from platform.startup.readiness import DependencyReadiness, DependencyState, report
from platform.startup.sequence import StartupResult, run_startup

_LOGGER = get_logger(__name__)

#: What the process exits with when configuration is wrong. Distinct from a
#: crash, because a supervisor that restarts on any non-zero exit will restart a
#: misconfigured deployment forever, and the log line saying why scrolls away.
CONFIGURATION_EXIT = 3


def readiness_of(health: StoreHealth) -> tuple[DependencyReadiness, ...]:
    """Return one readiness entry per dependency the store probe covered.

    The store's own health is one value; readiness wants it broken out, because
    "the database is up and the graph extension is not" and "the database is
    down" lead to different actions and only one of them takes the deployment
    out of rotation.
    """
    entries = [
        DependencyReadiness(
            name="database",
            state=DependencyState.READY if health.connected else DependencyState.UNAVAILABLE,
            detail="" if health.connected else "; ".join(health.reasons),
        ),
        DependencyReadiness(
            name="schema",
            state=(
                DependencyState.READY
                if health.migrations is not None and health.migrations.is_current
                else DependencyState.UNAVAILABLE
            ),
            detail=(
                ""
                if health.migrations is not None and health.migrations.is_current
                else "migrations have not finished"
            ),
        ),
    ]
    for extension in health.extensions:
        entries.append(
            DependencyReadiness(
                name=f"extension {extension.name}",
                state=(
                    DependencyState.READY if extension.available else DependencyState.UNAVAILABLE
                ),
                # The graph is the one this deployment degrades without: an
                # investigation with no blast radius is worse, not impossible.
                required=extension.name != "age",
                detail="" if extension.available else "not installed",
            )
        )
    if health.undecryptable_credentials:
        entries.append(
            DependencyReadiness(
                name="stored credentials",
                state=DependencyState.DEGRADED,
                detail=(
                    f"{len(health.undecryptable_credentials)} cannot be decrypted with "
                    f"the configured key"
                ),
            )
        )
    return tuple(entries)


async def _publish_model_bindings(deployment: Deployment) -> None:
    """Tell ``core.llm`` which provider and model each role is configured to run on.

    Configuration is resolved once here rather than per turn, because
    ``resolve_binding`` is synchronous and the answer changes when an operator
    saves a form, not between two calls in the same investigation.

    Advisory in both directions. A deployment that has configured nothing
    publishes nothing, every role falls through to the shipped default, and
    nothing in the environment gets a say — which is the state a deployment
    starts in, before anybody has been to the first-run screen. And a failure to
    read configuration is logged rather than raised: a console, a history and a
    health endpoint that all work are worth having up while somebody fixes the
    configuration tree.

    Note the ordering against ``run_startup`` in ``boot`` below. Validation runs
    first and cannot read any of this, because the database it would read is not
    open yet — which is why nothing it reports may describe a provider as
    *chosen*. The choice is made here, one step later.
    """
    try:
        scope = TenantScope(org_id=organisation_id())
        async with deployment.store.begin(scope) as uow:
            root = await uow.config.root()
        service = ConfigService(gateway=deployment.store, scope=scope)
        effective = await service.resolve(root.node_id)
        models = effective.values.get("models")
        if not isinstance(models, Mapping):
            publish_configured_bindings({})
            return
        bindings = {
            role: (str(bound.get("provider", "")), str(bound.get("model", "")))
            for role, bound in models.items()
            if isinstance(bound, Mapping) and bound.get("provider")
        }
        publish_configured_bindings(bindings)
        if bindings:
            _LOGGER.info("deployment.model_bindings", roles=sorted(bindings))
    except Exception as error:  # noqa: BLE001 — configuration must not stop a boot
        _LOGGER.warning("deployment.model_bindings_unavailable", error=str(error))
        publish_configured_bindings({})


async def boot(deployment: Deployment) -> StartupResult:
    """Run the startup sequence against ``deployment``'s store, and return what it found.

    Raises ``VaultKeyMismatch`` before any migration when the configured key
    does not open what is stored (FR-020), which is the whole reason the check
    is here rather than at the first credential read.

    The key is *loaded* before it is checked. Without that the check passed on
    every deployment that had stored nothing yet, and the ring was still empty
    when somebody wrote their first credential.
    """

    async def verify_credentials() -> None:
        health = await deployment.store.health()
        if health.undecryptable_credentials:
            raise VaultKeyMismatch(health.undecryptable_credentials)

    result = await run_startup(
        migrator=deployment.store.migrator(),
        install_key=deployment.store.install_encryption_key,
        verify_credentials=verify_credentials,
    )
    await _publish_model_bindings(deployment)
    health = await deployment.store.health()
    return StartupResult(
        topology=result.topology,
        validation=result.validation,
        migration=result.migration,
        readiness=report(readiness_of(health)),
        credentials_verified=result.credentials_verified,
        key_installed=result.key_installed,
    )


async def _serve(host: str, port: int, *, migrate_only: bool) -> None:
    """Compose, boot, and serve, all on one event loop.

    ``migrate_only`` is the Helm migration job: it runs the boot sequence,
    prints what it did, and exits without opening a listener. Still one loop and
    still under the same advisory lock, so it is safe alongside a replica of the
    previous release that restarts while it runs.
    """
    deployment = build_deployment()
    try:
        result = await boot(deployment)
        print(result.summary(), file=sys.stderr)  # noqa: T201 — a boot report is for a terminal
        if migrate_only:
            return

        # After the schema is at head and before the listener opens. Before,
        # because a credential issued against a schema this release refuses is a
        # credential written for a deployment that is about to exit; after,
        # because the operator must not meet a sign-in page there is no way past.
        entry = await bring_up(deployment.state.gateway, deployment.state.tokens)
        if entry.credential is not None:
            message = (
                announcement(entry.credential, path=credential_path())
                if entry.issued
                else (
                    f"Already brought up. The credential is unchanged and readable at "
                    f"{credential_path()}; it expires at "
                    f"{entry.credential.expires_at.isoformat()}."
                )
            )
        else:
            # This deployment already has a way in — a local administrator,
            # or an identity provider — so there is nothing to invite anybody
            # with.
            message = (
                "Already brought up, and administered: nothing to print. Sign in "
                "with an existing administrator, or run "
                f"{LOCAL_ADMIN_SETUP_COMMAND!r} to create or rotate one."
            )
        print(message, file=sys.stderr)  # noqa: T201 — the credential is printed, never logged (FR-004)

        # Cleared once the deployment is genuinely up. Otherwise the console
        # shows yesterday's failure to somebody whose deployment is working,
        # which is worse than showing nothing at all.
        forget_failure()

        server = uvicorn.Server(
            uvicorn.Config(create_app(deployment.state), host=host, port=port, log_config=None)
        )
        await server.serve()
    except BaseException as error:
        # Recorded before it is re-raised, so the console and the CLI can show
        # the same message the terminal did to somebody who was not watching it.
        record_failure(error, stage="bring-up")
        raise
    finally:
        if migrate_only:
            # The serving path hands the pool to the app's own lifespan, which
            # closes it at shutdown. A job that exits owns it itself.
            await deployment.store.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deployment. Returns the process exit code."""
    import argparse

    parser = argparse.ArgumentParser(prog="ninjasre-serve", description=__doc__)
    parser.add_argument("--host", default=DEFAULT_API_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="run the boot sequence and exit, without serving (the Helm migration job)",
    )
    arguments = parser.parse_args(argv)

    try:
        asyncio.run(_serve(arguments.host, arguments.port, migrate_only=arguments.migrate_only))
    except (StartupError, VaultKeyMismatch) as error:
        # Named, actionable, and a distinct exit code — a supervisor that
        # restarts on any failure would otherwise loop on a typo forever.
        _LOGGER.error("deployment.refused_to_start", reason=str(error))
        print(str(error), file=sys.stderr)  # noqa: T201 — the operator is reading a terminal
        print(  # noqa: T201
            f"Nothing has been changed. Fix the setting and start again; set "
            f"{NINJASRE_ADMIN_TOKEN_ENV} if you would rather choose the first "
            f"administrator's token yourself.",
            file=sys.stderr,
        )
        return CONFIGURATION_EXIT
    return 0


if __name__ == "__main__":  # pragma: no cover — the container's entrypoint
    raise SystemExit(main())


__all__ = ["CONFIGURATION_EXIT", "boot", "main", "readiness_of"]
