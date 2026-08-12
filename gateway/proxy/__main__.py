"""The credential proxy's process: ``python -m gateway.proxy``.

Deliberately does not migrate. The application owns the schema — one process
applying migrations under the advisory lock is the design (FR-007), and a proxy
that also migrated would be a second writer racing it for no benefit. What it
does do is verify the encryption key opens what is stored, because a proxy that
starts with the wrong key is a deployment where every authenticated call fails
during the first incident that needs one.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping, Sequence
from typing import Any

import uvicorn

from config.constants.surfaces import DEFAULT_API_HOST, DEFAULT_CREDENTIAL_PROXY_PORT
from gateway.proxy.composition import build_proxy_app
from gateway.proxy.hosts import hosts_from_configuration, with_configured_hosts
from platform.config_service.service import ConfigService
from platform.credentials.errors import VaultKeyMismatch
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope
from platform.persistence.postgres.crypto import KEY_RING
from platform.startup.bootstrap import organisation_id
from platform.startup.errors import StartupError

_LOGGER = get_logger(__name__)

#: Distinct from a crash, so a supervisor does not restart a typo forever.
CONFIGURATION_EXIT = 3


def install_encryption_key() -> bool:
    """Load the operator's key into this process, and say whether there was one.

    The proxy is the only thing that decrypts a credential, so a ring nobody
    loaded makes every forwarded call fail with "the key differs from the one
    that wrote it" — and the start-up check below cannot catch it, because with
    no key there is nothing for it to try.
    """
    return KEY_RING.configure_from_environment()


async def _configured_integrations(store: Any) -> tuple[Mapping[str, Any], ...]:
    """Return the active integration entries the configuration tree holds."""
    scope = TenantScope(org_id=organisation_id())
    config = ConfigService(gateway=store, scope=scope)
    effective = await config.resolve(scope.org_id)
    return tuple(
        {
            "name": getattr(entry, "name", ""),
            "enabled": getattr(entry, "enabled", True),
            "base_url": getattr(entry, "base_url", ""),
        }
        for entry in effective.config.integrations.active
    )


async def _serve(host: str, port: int) -> None:
    """Compose, check the key, and serve — all on one event loop."""
    app, store = build_proxy_app()

    # Before the check below, which cannot verify what has not been loaded.
    if not install_encryption_key():
        _LOGGER.warning("proxy.no_encryption_key")

    health = await store.health()
    if health.undecryptable_credentials:
        raise VaultKeyMismatch(health.undecryptable_credentials)

    # The operator's own addresses join the shipped allow-list, read from the
    # configuration tree where they were declared. Without this the proxy
    # refuses the very cluster the deployment was pointed at, because an
    # integration ships a placeholder host and nothing widened it.
    try:
        entries = await _configured_integrations(store)
    except Exception as unreadable:  # noqa: BLE001 — the proxy must still serve
        _LOGGER.warning("proxy.configuration_unreadable", error=str(unreadable))
    else:
        with_configured_hosts(app.engine.rules, hosts_from_configuration(entries))

    _LOGGER.info(
        "proxy.startup",
        integrations=len(app.engine.rules.integrations()),
    )

    try:
        await uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None)).serve()
    finally:
        await store.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the credential proxy. Returns the process exit code."""
    import argparse

    parser = argparse.ArgumentParser(prog="ninjasre-proxy", description=__doc__)
    parser.add_argument("--host", default=DEFAULT_API_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_CREDENTIAL_PROXY_PORT)
    arguments = parser.parse_args(argv)

    try:
        asyncio.run(_serve(arguments.host, arguments.port))
    except (StartupError, VaultKeyMismatch) as error:
        _LOGGER.error("proxy.refused_to_start", reason=str(error))
        print(str(error), file=sys.stderr)  # noqa: T201 — the operator is reading a terminal
        return CONFIGURATION_EXIT
    return 0


if __name__ == "__main__":  # pragma: no cover — the container's entrypoint
    raise SystemExit(main())


__all__ = ["CONFIGURATION_EXIT", "main"]
