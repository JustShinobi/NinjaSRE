"""Redis Cloud's credential shape, hosts, and how its secret enters a request.

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

INTEGRATION: Final = "redis"


#: Every host Redis Cloud serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap.single(INTEGRATION, host="api.redislabs.com", name="global")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "api_key",
        "Redis Cloud account key",
        min_length=8,
        label="Account key",
        # The account key only identifies the account; Redis Cloud's own
        # permission model lives on the secret key's associated user, which is
        # why that field below carries the real scope and this one does not.
        min_scope="this token does not carry scope — treat it as full access",
        guide_url="https://redis.io/docs/latest/operate/rc/api/get-started/",
    ),
    secret(
        "secret_key",
        "Redis Cloud user secret key",
        min_length=8,
        label="Secret key",
        min_scope="subscriptions:read",
        guide_url="https://redis.io/docs/latest/operate/rc/api/get-started/",
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        HeaderInjection(header="x-api-key", field="api_key", template="{value}"),
        HeaderInjection(header="x-api-secret-key", field="secret_key"),
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
