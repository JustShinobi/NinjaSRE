"""Composing "what is out there" from the configuration tree, at startup.

A discovery source needs three things that live in three places: a setting
(which cluster, at which address), a client the credential proxy can build, and
the reader that turns a vendor's answer into resources. Only a composition root
has all three, and this is where the gateway's is — beside the change sources,
which solve the same shape of problem the same way.

**It is read from the configuration tree rather than from the environment.**
Which cluster a deployment watches is a fact about the operator's estate, and
the estate's facts are edited where there is provenance, a preview and an audit
row. An environment variable would need a restart and would leave no record of
who pointed it somewhere else.

**Resolved at the root, once.** ``GatewayState`` is per process, and a source is
a client and an address rather than a per-request decision.

**A misconfiguration does not stop the gateway.** A cluster nothing can reach is
logged and skipped, because the console somebody would fix it from is served by
this same process — and a deployment that refuses to start over one optional
setting is one nobody can correct.

**Nothing here holds a credential.** The client is built over the credential
proxy's transport, which resolves the secret by handle at call time. This module
names the integration and the address, and never learns the token.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.state import GatewayState
from integrations._base.transport import HttpProxyTransport, RequestContext
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import ProxmoxDiscovery
from platform.config_service.service import ConfigService
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope

logger = get_logger(__name__)

#: What the proxy is told is asking, so a forwarded call is attributable.
DISCOVERY_CAPABILITY = "estate.discovery"

#: The integrations this deployment knows how to sweep, by name. A source is a
#: reader plus a client, and only the reader differs — so adding a second vendor
#: is a row here rather than a branch below.
_BUILDERS: Mapping[str, Any] = {"proxmox": (ProxmoxClient, ProxmoxDiscovery)}


async def _active_integrations(state: GatewayState, org_id: str) -> tuple[Mapping[str, Any], ...]:
    """Return the active integration entries the configuration tree holds.

    Separated so a test can drive the composition without a database: what is
    interesting here is which entries become sources, not how a document is
    read.
    """
    scope = TenantScope(org_id=org_id)
    config = ConfigService(gateway=state.gateway, scope=scope)
    effective = await config.resolve(org_id)
    active = effective.config.integrations.active
    return tuple(entry if isinstance(entry, Mapping) else _as_mapping(entry) for entry in active)


def _as_mapping(entry: Any) -> Mapping[str, Any]:
    """Return a settings object as the mapping this module reads."""
    return {
        "name": getattr(entry, "name", ""),
        "enabled": getattr(entry, "enabled", True),
        "base_url": getattr(entry, "base_url", ""),
    }


def _endpoints(base_url: str) -> Sequence[str]:
    """Return the host a base URL names, as the client's endpoint ring wants it."""
    trimmed = base_url.strip()
    if not trimmed:
        return ()
    without_scheme = trimmed.split("://", 1)[-1]
    return (without_scheme.strip("/"),)


async def compose_discovery_sources(
    state: GatewayState, *, org_id: str, proxy_url: str
) -> Mapping[str, Any]:
    """Put this deployment's configured discovery sources on ``state``.

    Returns what was composed, so a caller can log it. An entry that is switched
    off, names an integration nothing here sweeps, or carries no address is
    skipped with a line saying which and why — a source pointed nowhere fails at
    the first sweep instead, which is further from the person who configured it.
    """
    if not proxy_url:
        # A source reaches its vendor through the proxy and never around it, so
        # a deployment without one composes nothing rather than a client that
        # would have to hold a credential itself.
        logger.info("discovery.sources_skipped", reason="no credential proxy is configured")
        return {}

    try:
        entries = await _active_integrations(state, org_id)
    except Exception as unreadable:  # noqa: BLE001 — an optional source must not stop a boot
        logger.warning("discovery.sources_unreadable", error=str(unreadable))
        return {}

    transport = HttpProxyTransport(base_url=proxy_url)
    # The organisation's own handle, not an empty team. A sweep is the
    # deployment's, not one team's, and the credential a team-less token wrote
    # went to the organisation-wide handle — asking for "" would build a handle
    # the grammar refuses and be turned away at the proxy.
    context = RequestContext(
        org_id=org_id, team_id=CREDENTIAL_ORG_WIDE_TEAM, capability=DISCOVERY_CAPABILITY
    )

    composed: dict[str, Any] = {}
    for entry in entries:
        name = str(entry.get("name", ""))
        builders = _BUILDERS.get(name)
        if builders is None:
            continue
        if not bool(entry.get("enabled", True)):
            logger.info("discovery.source_disabled", integration=name)
            continue
        endpoints = _endpoints(str(entry.get("base_url", "")))
        if not endpoints:
            logger.warning("discovery.source_unaddressed", integration=name)
            continue
        client_type, reader_type = builders
        composed[name] = reader_type(
            client=client_type(transport=transport, context=context, endpoints=endpoints)
        )

    state.discovery_sources = composed
    logger.info("discovery.sources_composed", integrations=sorted(composed))
    return composed


__all__ = ["DISCOVERY_CAPABILITY", "compose_discovery_sources"]
