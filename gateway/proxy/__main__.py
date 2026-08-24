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
from contextlib import suppress
from typing import Any

import uvicorn

from config.constants.surfaces import DEFAULT_API_HOST, DEFAULT_CREDENTIAL_PROXY_PORT
from gateway.proxy.composition import build_proxy_app
from gateway.proxy.hosts import (
    bridge_hosts,
    hosts_from_configuration,
    refresh_configured_hosts,
    refresh_configured_trust,
    trust_from_configuration,
    with_configured_hosts,
)
from integrations.registry import injection_rules
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

#: How often the allow-list is re-read from the configuration tree.
#:
#: The addresses an operator configures are the only part of the rule that is
#: not compiled in, and reading them once at start-up made an address entered in
#: the console take effect at the next restart — which is a pod restart for a
#: reason nothing on the screen explains. A minute is short enough that nobody
#: waits on it and long enough that it is one query per proxy per minute.
HOST_REFRESH_SECONDS = 60


def install_encryption_key() -> bool:
    """Load the operator's key into this process, and say whether there was one.

    The proxy is the only thing that decrypts a credential, so a ring nobody
    loaded makes every forwarded call fail with "the key differs from the one
    that wrote it" — and the start-up check below cannot catch it, because with
    no key there is nothing for it to try.
    """
    return KEY_RING.configure_from_environment()


async def _configured_egress(store: Any) -> tuple[dict[str, tuple[str, ...]], tuple[Any, ...]]:
    """Return the hosts the configuration points at, and what it trusts at each.

    One read producing both, deliberately. They are two facts about the same
    entry — where the vendor is, and what this deployment accepts from the
    certificate found there — and deriving them from two reads is how they come
    to describe different documents.

    Two places for the hosts, because the configuration has two. An integration
    entry carries the address it is pointed at; the observability bridge names
    its metrics and log systems in the policy tree. Reading only the first left
    an operator who had configured their own Loki refused for reaching a host
    the integration had not declared — correctly configured, and refused anyway.
    """
    scope = TenantScope(org_id=organisation_id())
    config = ConfigService(gateway=store, scope=scope)
    effective = await config.resolve(scope.org_id)

    entries = tuple(
        {
            "name": getattr(entry, "name", ""),
            "enabled": getattr(entry, "enabled", True),
            "base_url": getattr(entry, "base_url", ""),
            "trust": _trust_record(entry),
        }
        for entry in effective.config.integrations.active
    )
    hosts = hosts_from_configuration(entries)
    for name, found in bridge_hosts(effective.config.policies.observation.bridge).items():
        hosts[name] = tuple(dict.fromkeys((*hosts.get(name, ()), *found)))
    return hosts, trust_from_configuration(entries)


def _trust_record(entry: Any) -> Mapping[str, Any]:
    """Return an entry's certificate-trust section as a plain document."""
    declared = getattr(entry, "trust", None)
    if declared is None:
        return {}
    if isinstance(declared, Mapping):
        return dict(declared)
    dumped = getattr(declared, "model_dump", None)
    return dict(dumped(exclude_none=True)) if dumped is not None else {}


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
        hosts, trusted = await _configured_egress(store)
    except Exception as unreadable:  # noqa: BLE001 — the proxy must still serve
        _LOGGER.warning("proxy.configuration_unreadable", error=str(unreadable))
    else:
        with_configured_hosts(app.engine.rules, hosts)
        # The same read, applied at the same moment. Without this the first
        # minute of every process verifies a self-signed cluster against the
        # system store and refuses every call to it, which reads as an outage
        # rather than as a cycle that has not run yet.
        refresh_configured_trust(app.engine.trust, trusted)

    _LOGGER.info(
        "proxy.startup",
        integrations=len(app.engine.rules.integrations()),
        trusted_addresses=len(app.engine.trust.hosts()),
    )

    watching = asyncio.create_task(_watch_configured_hosts(app, store))
    try:
        await uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None)).serve()
    finally:
        # Awaited, not just cancelled: a pending task nobody collected prints a
        # warning at interpreter shutdown that reads like a bug in the proxy.
        watching.cancel()
        with suppress(asyncio.CancelledError):
            await watching
        await store.close()


async def _watch_configured_hosts(app: Any, store: Any) -> None:
    """Keep the allow-list and the trust following the configuration, not the process age.

    Both, from one read, in one cycle. Where a vendor is and what is accepted
    from its certificate are two facts about one entry, and two cycles deriving
    them separately is how they end up describing different documents.

    Rebuilt from the shipped rules each time rather than widened, so an address
    an operator removed stops being reachable — a permission that outlived the
    decision to grant it is the failure this exists to avoid, and it is the one
    a widen-only refresh would still have.

    An unreadable configuration leaves the current rules in place and logs it.
    The proxy's job is to keep forwarding what is already permitted; refusing
    every call because one read failed would turn a transient database blip into
    an outage of every integration.
    """
    declared = injection_rules()
    shipped = tuple(declared.get(name) for name in declared.integrations())
    while True:
        await asyncio.sleep(HOST_REFRESH_SECONDS)
        try:
            hosts, trusted = await _configured_egress(store)
        except Exception as unreadable:  # noqa: BLE001 — the proxy must still serve
            _LOGGER.warning("proxy.configuration_unreadable", error=str(unreadable))
            continue
        refresh_configured_hosts(app.engine.rules, shipped=shipped, hosts=hosts)
        refresh_configured_trust(app.engine.trust, trusted)


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
