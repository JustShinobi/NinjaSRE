"""Composing "where the logs are" from the configuration tree, at startup.

The third source of this shape, and it is wired the same way as the change and
discovery sources for the same reasons: read from the configuration tree so an
operator edits it with provenance and an audit row, resolved once at the root
because a log system is a deployment-wide address rather than a per-request
decision, and skipped with a line rather than fatally when there is nothing to
build.

**Nothing here holds a credential.** The client is built over the credential
proxy's transport, which resolves the secret by handle at call time.

**The selector rules come from configuration too.** A deployment whose log
shipper labels streams some third way writes its own rule and it works. The
shipped defaults assume the journal's own ``job`` label, which is right for a
stock install and wrong for anyone who configured their shipper differently —
so it is a setting, not a constant.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from capabilities.tools.logs import binding
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.state import GatewayState
from integrations._base.transport import HttpProxyTransport, RequestContext
from integrations.loki.client import LokiClient
from integrations.loki.log_source import LokiLogSource
from platform.config_service.service import ConfigService
from platform.estate.service import EstateService
from platform.observability.logging import get_logger
from platform.observation.bridge.catalogue import SHIPPED_LOG_SELECTORS, LogSelectorRule
from platform.observation.bridge.logs import LogAnswer, LogReader
from platform.persistence.ports import TenantScope

logger = get_logger(__name__)

#: What the proxy is told is asking when a log line is read.
LOGS_CAPABILITY = "logs.read"


def selector_rules_from(settings: Any) -> tuple[LogSelectorRule, ...]:
    """Return the selector rules this deployment declared, shipped ones included.

    The operator's own rules come first, so a deployment that declared a rule for
    a kind the shipped defaults also cover gets theirs — which is the point of
    being able to declare one.
    """
    declared = tuple(
        LogSelectorRule(
            rule_id=str(getattr(rule, "rule_id", "")),
            resource_kind=str(getattr(rule, "resource_kind", "")),
            template=str(getattr(rule, "template", "")),
            description=str(getattr(rule, "description", "")),
        )
        for rule in getattr(settings, "log_selectors", ()) or ()
    )
    shipped = SHIPPED_LOG_SELECTORS if getattr(settings, "use_shipped_log_selectors", True) else ()
    return declared + tuple(shipped)


@dataclass(frozen=True, slots=True)
class ComposedLogAccess:
    """What the log capability asks, wired to this deployment's source.

    The resource lookup is on this side of the seam for the reason the change
    access gives: resolving "which resource is this" needs the estate and a
    tenant scope, and the capability layer is allowed neither.
    """

    estate: EstateService
    scope: TenantScope
    reader: LogReader
    rules: Sequence[LogSelectorRule]

    def selector_for(self, resource: Any) -> str:
        """Return the first declared selector that applies, or empty for none."""
        for rule in self.rules:
            if rule.resource_kind == getattr(resource, "kind", ""):
                selector = rule.selector_for(resource)
                if selector:
                    return selector
        return ""

    async def logs_for(self, resource: str, *, at: datetime) -> LogAnswer | None:
        """Return what ``resource``'s stream held, or ``None`` when it has none."""
        detail = await self.estate.detail(self.scope, resource, now=at)
        if detail is None:
            return None
        selector = self.selector_for(detail.view.resource)
        if not selector:
            # A resource whose kind no rule covers, or whose identity could not
            # fill the template. Both are "nothing to read", never an empty
            # answer — a query built from a half-filled template matches
            # everything or nothing, and neither is about this resource.
            logger.info("logs.no_selector", resource=resource)
            return None
        return await self.reader.read(selector, at=at)


async def compose_log_sources(
    state: GatewayState, *, org_id: str, proxy_url: str
) -> tuple[Any, ...]:
    """Put this deployment's configured log source on ``state`` and bind the tool.

    Binds the capability only when something was composed: an unbound tool
    reports that no log source is configured, which is an answer an operator can
    act on — a bound tool over no source would report "nothing was logged".
    """
    if not proxy_url:
        logger.info("logs.sources_skipped", reason="no credential proxy is configured")
        binding.bind(None)
        return ()

    scope = TenantScope(org_id=org_id)
    try:
        effective = await ConfigService(gateway=state.gateway, scope=scope).resolve(org_id)
        bridge = effective.config.policies.observation.bridge
        rules = selector_rules_from(bridge)
    except Exception as unreadable:  # noqa: BLE001 — an optional source must not stop a boot
        logger.warning("logs.sources_unreadable", error=str(unreadable))
        binding.bind(None)
        return ()

    transport = HttpProxyTransport(base_url=proxy_url)
    context = RequestContext(
        org_id=org_id, team_id=CREDENTIAL_ORG_WIDE_TEAM, capability=LOGS_CAPABILITY
    )

    composed: list[Any] = []
    settings = bridge.logs
    endpoint = str(settings.endpoint).strip()
    if not settings.enabled:
        logger.info("logs.source_disabled", reason="the bridge's log source is switched off")
    elif not endpoint:
        # Pointed nowhere fails at the first query instead, which is further from
        # whoever configured it.
        logger.warning("logs.source_unaddressed")
    else:
        composed.append(
            LokiLogSource(
                client=LokiClient(transport=transport, context=context, base_url=endpoint)
            )
        )

    state.log_sources = tuple(composed)
    logger.info("logs.sources_composed", count=len(composed))

    binding.bind(
        None
        if not composed
        else ComposedLogAccess(
            estate=EstateService(gateway=state.gateway, kinds=state.estate_kinds),
            scope=scope,
            reader=LogReader(source=composed[0]),
            rules=rules,
        )
    )
    return tuple(composed)


__all__ = ["LOGS_CAPABILITY", "ComposedLogAccess", "compose_log_sources", "selector_rules_from"]
