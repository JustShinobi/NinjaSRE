"""Honeycomb's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, public, secret
from platform.credentials.proxy.injection import (
    HeaderInjection,
    InjectionRule,
    PathSegmentInjection,
)

INTEGRATION: Final = "honeycomb"


#: Every host Honeycomb serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap(
    integration=INTEGRATION,
    regions=(
        Region(name="us", host="api.honeycomb.io", display_name="United States"),
        Region(name="eu", host="api.eu1.honeycomb.io", display_name="Europe"),
    ),
    default="us",
)

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "api_key",
        "Honeycomb API key with query access to the datasets you investigate",
        min_length=8,
    ),
    public("dataset", "The dataset this integration queries", required=True),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        HeaderInjection(header="X-Honeycomb-Team", field="api_key", template="{value}"),
        PathSegmentInjection(placeholder="dataset", field="dataset"),
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
