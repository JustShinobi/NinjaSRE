"""Pushover's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import RegionMap
from integrations._base.schema import credential_schema, secret
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule

INTEGRATION: Final = "pushover"


#: Every host Pushover serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap.single(INTEGRATION, host="api.pushover.net", name="global")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "token",
        "Pushover application API token",
        min_length=8,
        label="Application token",
        guide_url="https://pushover.net/apps/build",
    ),
    secret(
        "user_key",
        "Pushover user or group key",
        min_length=8,
        label="User or group key",
        guide_url="https://pushover.net/",
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        HeaderInjection(header="X-Pushover-Token", field="token", template="{value}"),
        HeaderInjection(header="X-Pushover-User", field="user_key"),
    ),
)


def base_url(region: str = "") -> str:
    """Return the API base URL for a region, or for the default one."""
    return REGIONS.base_url(region)


__all__ = [
    "HOSTS",
    "INTEGRATION",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "base_url",
]
