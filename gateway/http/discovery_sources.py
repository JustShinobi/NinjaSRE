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
from integrations.prometheus.client import PrometheusClient
from integrations.prometheus.metrics_query import PrometheusMetrics
from integrations.prometheus.schema import INTEGRATION as PROMETHEUS
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import ProxmoxDiscovery
from platform.config_service.service import ConfigService
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope

logger = get_logger(__name__)

#: What the proxy is told is asking, so a forwarded call is attributable.
DISCOVERY_CAPABILITY = "estate.discovery"

#: What the proxy is told is asking when a signal is read.
OBSERVATION_CAPABILITY = "observation.tick"

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
    """Return the bare host a base URL names, as the client's endpoint ring wants it.

    Without the port: a vendor client builds its own base URL from the host and
    the port it knows, so a host that arrives carrying one produces an address
    with two — and a name no resolver has.
    """
    trimmed = base_url.strip()
    if not trimmed:
        return ()
    authority = trimmed.split("://", 1)[-1].split("/", 1)[0]
    if authority.startswith("["):
        # An IPv6 literal is bracketed, and its colons are not a port separator.
        return (authority.partition("]")[0].lstrip("["),)
    host = authority.split(":", 1)[0]
    return (host,) if host else ()


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


async def compose_signal_sources(
    state: GatewayState, *, org_id: str, proxy_url: str
) -> tuple[Any, ...]:
    """Put the metrics clients this deployment configured on ``state``.

    The same shape and the same reasoning as the discovery sources above: read
    from the configuration tree, built over the credential proxy, and skipped
    with a line rather than fatally when there is nothing to build.

    What is composed is a *client*, not a source. The source needs the estate's
    guests, which change with every sweep, so it is built per tick by the job
    that polls — and this hands it the thing that can answer a query.
    """
    if not proxy_url:
        logger.info("observation.sources_skipped", reason="no credential proxy is configured")
        return ()

    try:
        entries = await _active_integrations(state, org_id)
    except Exception as unreadable:  # noqa: BLE001 — an optional source must not stop a boot
        logger.warning("observation.sources_unreadable", error=str(unreadable))
        return ()

    transport = HttpProxyTransport(base_url=proxy_url)
    context = RequestContext(
        org_id=org_id, team_id=CREDENTIAL_ORG_WIDE_TEAM, capability=OBSERVATION_CAPABILITY
    )

    composed: list[Any] = []
    for entry in entries:
        if str(entry.get("name", "")) != PROMETHEUS or not bool(entry.get("enabled", True)):
            continue
        composed.append(
            PrometheusMetrics(client=PrometheusClient(transport=transport, context=context))
        )

    state.signal_sources = tuple(composed)
    logger.info("observation.sources_composed", count=len(composed))
    return tuple(composed)


__all__ = [
    "DISCOVERY_CAPABILITY",
    "OBSERVATION_CAPABILITY",
    "compose_discovery_sources",
    "compose_signal_sources",
]
