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

from platform.config_service.schema.integrations import CertificateTrustSettings
from platform.credentials.proxy.injection import InjectionRule, InjectionRuleRegistry
from platform.credentials.proxy.trust import CertificateTrust, TrustAnchor, TrustRegistry
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


def bridge_hosts(bridge: Any) -> dict[str, tuple[str, ...]]:
    """Return the hosts the observability bridge's sources are pointed at.

    The bridge names its metrics and log systems in the policy tree rather than
    in the active-integration list, so reading only that list left an operator
    who had configured their own Loki refused for reaching a host the
    integration had not declared. An endpoint is an integration endpoint
    wherever it is written down.

    A source switched off contributes nothing, and one naming no integration
    contributes nothing: registering a rule for either would open egress that
    no integration asked for.
    """
    found: dict[str, tuple[str, ...]] = {}
    for attribute in ("metrics", "logs"):
        source = getattr(bridge, attribute, None)
        if source is None or not bool(getattr(source, "enabled", False)):
            continue
        name = str(getattr(source, "name", "") or "").strip()
        host = _host_of(str(getattr(source, "endpoint", "") or ""))
        if name and host:
            found[name] = (*found.get(name, ()), host)
    return found


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


def trust_from_configuration(
    entries: Iterable[Mapping[str, Any]],
) -> tuple[CertificateTrust, ...]:
    """Return what each active integration accepts from its endpoint's certificate.

    Read from the same entries the hosts come from, in the same pass, because
    two truths derived from one document by two readers is how they come to
    disagree about the same address.

    An entry that declared nothing contributes nothing: the registry's own
    fallback is the system trust store, so the safe default costs no row. An
    entry with no address contributes nothing either — a declaration that names
    no address authorises no address, which is what makes moving the address
    invalidate the decision taken for the one before it.

    A declaration that does not parse is dropped with a line naming the
    integration, and the rest are kept. One malformed entry costing every other
    integration its declaration would turn a typo into a deployment-wide
    downgrade nobody chose.
    """
    found: list[CertificateTrust] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        if not name or not bool(entry.get("enabled", True)):
            continue
        address = str(entry.get("base_url", "")).strip()
        declared = entry.get("trust")
        if not address or not isinstance(declared, Mapping) or not declared:
            continue
        try:
            trust = CertificateTrustSettings.model_validate(dict(declared)).declaration(address)
        except ValueError as refused:
            logger.warning("proxy.trust_declaration_refused", integration=name, error=str(refused))
            continue
        if trust.anchor is TrustAnchor.SYSTEM_TRUST_STORE:
            continue
        found.append(trust)
    return tuple(found)


def refresh_configured_trust(
    trust: TrustRegistry, declarations: Iterable[CertificateTrust]
) -> TrustRegistry:
    """Rebuild what the egress trusts from ``declarations``, discarding what it held.

    Rebuild rather than widen, for the reason the allow-list rebuild gives: a
    declaration an operator removed has to stop applying at the next cycle, and
    a registry that had only ever been added to cannot express that. A trust
    decision that outlived the decision to take it is the same failure as a
    permission that did.
    """
    before = trust.hosts()
    trust.replace_all(declarations)
    after = trust.hosts()
    if before != after:
        logger.info("proxy.trust_rebuilt", addresses=sorted(after))
    return trust


def refresh_configured_hosts(
    rules: InjectionRuleRegistry,
    *,
    shipped: Iterable[InjectionRule],
    hosts: Mapping[str, Sequence[str]],
) -> InjectionRuleRegistry:
    """Rebuild the allow-list from ``shipped`` and re-apply what is configured now.

    ``with_configured_hosts`` below only ever widens, which is right the first
    time and wrong every time after: the module promises that switching an
    integration off closes what it opened, and a registry that has only been
    widened cannot close anything. Put back what the packages declare, then
    apply what the configuration says today, and the reachable set follows the
    configuration rather than outliving it.

    This is what lets an address entered in the console take effect on the next
    call. Read only at start-up, the proxy refuses the very cluster an operator
    has just pointed it at, and the fix looks like restarting a pod for a reason
    nothing on the screen explains.
    """
    for rule in shipped:
        rules.register(rule)
    return with_configured_hosts(rules, hosts)


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


__all__ = [
    "bridge_hosts",
    "hosts_from_configuration",
    "refresh_configured_hosts",
    "refresh_configured_trust",
    "trust_from_configuration",
    "with_configured_hosts",
]
