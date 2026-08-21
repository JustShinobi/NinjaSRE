"""Coralogix's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, secret
from platform.credentials.proxy.injection import BearerTokenInjection, InjectionRule

INTEGRATION: Final = "coralogix"


#: Every host Coralogix serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap(
    integration=INTEGRATION,
    regions=(
        Region(name="eu1", host="api.coralogix.com", display_name="Ireland"),
        Region(name="eu2", host="api.eu2.coralogix.com", display_name="Sweden"),
        Region(name="us1", host="api.coralogix.us", display_name="United States"),
        Region(name="us2", host="api.cx498.coralogix.com", display_name="United States (west)"),
        Region(name="ap1", host="api.app.coralogix.in", display_name="India"),
        Region(name="ap2", host="api.coralogixsg.com", display_name="Singapore"),
    ),
    default="eu1",
)

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret("token", "Coralogix API key with DataQuerying permission", min_length=8),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(BearerTokenInjection(field="token"),),
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
