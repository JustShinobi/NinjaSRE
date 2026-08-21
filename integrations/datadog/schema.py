"""Datadog's credential shape, hosts, and how its keys enter a request.

The reference case for the simplest row of FR-018's table: Datadog's API is
REST, its authentication is two headers, and its Python SDK is a thin wrapper
over both. There is nothing for an SDK to do that ``integrations/_base`` does
not already do, so there is no SDK — which also means there is no vendor library
in the dependency tree that could decide to read ``DD_API_KEY`` from the
environment on some future upgrade.

Two credential fields rather than one, because Datadog uses both and an
integration that injected only the API key would work for metrics and fail for
everything that needs an application key. The schema declares both as required,
so a half-configured integration is rejected at the moment it is entered.

``site`` is the one part of a Datadog configuration a capability may legitimately
see. It is not a secret — it is which regional deployment the organisation is
on — and it is what makes the host list below three entries rather than one.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind

INTEGRATION: Final = "datadog"

API_KEY_HEADER: Final = "DD-API-KEY"
APPLICATION_KEY_HEADER: Final = "DD-APPLICATION-KEY"

#: The regional deployments Datadog serves the API from. Listed rather than
#: pattern-matched: ``*.datadoghq.com`` would permit any subdomain, including
#: one an attacker controls the day Datadog delegates a zone. Datadog's site
#: names and its host names do not follow one pattern — ``datadoghq.eu`` has no
#: region segment and the government site has a different domain entirely — so
#: this is a declared map rather than a template (FR-007).
REGIONS: Final = RegionMap(
    integration=INTEGRATION,
    regions=(
        Region(name="datadoghq.com", host="api.datadoghq.com", display_name="US1"),
        Region(name="datadoghq.eu", host="api.datadoghq.eu", display_name="EU1"),
        Region(name="us3.datadoghq.com", host="api.us3.datadoghq.com", display_name="US3"),
        Region(name="us5.datadoghq.com", host="api.us5.datadoghq.com", display_name="US5"),
        Region(name="ap1.datadoghq.com", host="api.ap1.datadoghq.com", display_name="AP1"),
        Region(name="ddog-gov.com", host="api.ddog-gov.com", display_name="US1-FED"),
    ),
    default="datadoghq.com",
)

#: The egress allow-list, which is the region map and not a second tuple. Two
#: lists is how an integration ends up permitted to reach a region it can no
#: longer name.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

#: Datadog keys are 32 hex characters and application keys are 40. The patterns
#: are worth declaring because both are pasted by hand, and the common failure —
#: a truncated paste — produces a key that looks plausible and fails at 03:00.
SCHEMA: Final = CredentialSchema(
    integration=INTEGRATION,
    fields=(
        CredentialField(
            name="api_key",
            description="Datadog API key, from Organisation Settings → API Keys.",
            pattern=r"[0-9a-f]{32}",
        ),
        CredentialField(
            name="app_key",
            description="Datadog application key, from Organisation Settings → Application Keys.",
            pattern=r"[0-9a-zA-Z]{40}",
        ),
        CredentialField(
            name="site",
            description="Regional site, such as datadoghq.com or datadoghq.eu.",
            kind=FieldKind.PUBLIC,
            required=False,
        ),
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        HeaderInjection(header=API_KEY_HEADER, field="api_key"),
        HeaderInjection(header=APPLICATION_KEY_HEADER, field="app_key"),
    ),
)


def base_url(site: str = "") -> str:
    """Return the API base URL for a Datadog regional site.

    Resolved through the region map rather than by string interpolation, so a
    site nobody declared is refused here — with the list of the ones that
    exist — instead of producing a host the proxy silently declines.
    """
    return REGIONS.base_url(site)


__all__ = [
    "API_KEY_HEADER",
    "APPLICATION_KEY_HEADER",
    "HOSTS",
    "INTEGRATION",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "base_url",
]
