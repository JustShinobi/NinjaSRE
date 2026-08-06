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

from platform.credentials.proxy.injection import HeaderInjection, InjectionRule
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind

INTEGRATION: Final = "datadog"

API_KEY_HEADER: Final = "DD-API-KEY"
APPLICATION_KEY_HEADER: Final = "DD-APPLICATION-KEY"

#: The regional deployments Datadog serves the API from. Listed rather than
#: pattern-matched: ``*.datadoghq.com`` would permit any subdomain, including
#: one an attacker controls the day Datadog delegates a zone.
HOSTS: Final[tuple[str, ...]] = (
    "api.datadoghq.com",
    "api.datadoghq.eu",
    "api.us3.datadoghq.com",
    "api.us5.datadoghq.com",
    "api.ap1.datadoghq.com",
    "api.ddog-gov.com",
)

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


def base_url(site: str = "datadoghq.com") -> str:
    """Return the API base URL for a Datadog regional site."""
    return f"https://api.{site}"


__all__ = [
    "API_KEY_HEADER",
    "APPLICATION_KEY_HEADER",
    "HOSTS",
    "INTEGRATION",
    "RULE",
    "SCHEMA",
    "base_url",
]
