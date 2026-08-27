"""GitHub's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, endpoint, public, secret
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule

INTEGRATION: Final = "github"


#: Every host GitHub serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap(
    integration=INTEGRATION,
    regions=(
        Region(name="github.com", host="api.github.com", display_name="github.com"),
        Region(
            name="enterprise", host="github.example.com", display_name="GitHub Enterprise Server"
        ),
    ),
    default="github.com",
)

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    endpoint(
        "endpoint",
        "Only for GitHub Enterprise Server — https://github.acme.example/api/v3. "
        "Leave empty for github.com.",
        required=False,
        label="Enterprise Server address",
        guide_url=(
            "https://docs.github.com/en/enterprise-server@latest/admin/overview/"
            "about-github-enterprise-server"
        ),
    ),
    secret(
        "token",
        "GitHub token — a fine-grained personal access token or an app installation token",
        min_length=8,
        label="Personal access token",
        min_scope="Repository permissions: Contents (read-only) and Pull requests (read-only)",
        guide_url=(
            "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/"
            "managing-your-personal-access-tokens"
        ),
    ),
    public(
        "owner",
        "Default organisation or user the repositories belong to",
        label="Default owner",
        guide_url=(
            "https://docs.github.com/en/organizations/collaborating-with-groups-in-organizations/"
            "about-organizations"
        ),
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(HeaderInjection(header="Authorization", field="token", template="Bearer {value}"),),
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
