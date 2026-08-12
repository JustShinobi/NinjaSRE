"""The egress allow-list, extended by the addresses an operator configured.

Every integration ships the hosts it may reach, and that list is the boundary
prompt injection cannot cross: a client cannot address somewhere its integration
never declared. The shipped entry is necessarily a placeholder — nobody
packaging an integration knows where your cluster is.

So the operator's own declaration has to reach the proxy, and the configuration
tree is where they make it: an active integration carries the address it is
pointed at, with provenance, a preview and an audit row behind the change. This
module is the translation between that document and the rule the proxy enforces.

**It extends rather than replaces.** The shipped host stays permitted, because a
deployment may reach a vendor's public API *and* an appliance of its own.

**It invents nothing.** An entry naming an integration this build does not
declare is ignored: registering a rule for it would open egress that no
integration asked for, which is the one thing an allow-list must never do.

**Switching an integration off closes what it opened.** A disabled entry
contributes no host, so the reachable set follows the configuration rather than
outliving it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _host_of(base_url: str) -> str:
    """Return the bare host an address names, without scheme, port or path.

    A rule refuses a ``host:port`` entry and says why — the port is not a
    security boundary, and including one makes the list wrong the first time a
    vendor moves. So the port is dropped here rather than rejected there.
    """
    trimmed = base_url.strip()
    if not trimmed:
        return ""
    without_scheme = trimmed.split("://", 1)[-1]
    authority = without_scheme.split("/", 1)[0]
    # An IPv6 literal is bracketed, and its colons are not a port separator.
    if authority.startswith("["):
        return authority.partition("]")[0].lstrip("[")
    return authority.split(":", 1)[0]


def hosts_from_configuration(
    entries: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[str, ...]]:
    """Return the hosts each active integration is pointed at, by integration."""
    found: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        name = str(entry.get("name", ""))
        if not name or not bool(entry.get("enabled", True)):
            continue
        host = _host_of(str(entry.get("base_url", "")))
        if not host:
            continue
        found[name] = (*found.get(name, ()), host)
    return found


def with_configured_hosts(
    rules: InjectionRuleRegistry, hosts: Mapping[str, Sequence[str]]
) -> InjectionRuleRegistry:
    """Extend each declared rule's allow-list with the addresses configured for it.

    Returns the same registry, mutated, so a caller composing an engine can pass
    it straight through.
    """
    for integration, addresses in hosts.items():
        if not rules.has(integration):
            logger.warning("proxy.configured_host_undeclared", integration=integration)
            continue
        rule = rules.get(integration)
        widened = tuple(sorted({*rule.hosts, *addresses}))
        if widened == rule.hosts:
            continue
        rules.register(replace(rule, hosts=widened))
        logger.info("proxy.egress_extended", integration=integration, hosts=sorted(addresses))
    return rules


__all__ = ["hosts_from_configuration", "with_configured_hosts"]
