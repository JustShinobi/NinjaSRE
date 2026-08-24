"""Grafana's credential shape, hosts, and how its secret enters a request.

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
from platform.credentials.proxy.injection import BearerTokenInjection, InjectionRule

INTEGRATION: Final = "grafana"


#: Where a default install serves its API. See ``rule_for``.
DEFAULT_HOST: Final = "grafana.example.com"

#: Every host Grafana serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap.single(INTEGRATION, host="grafana.example.com", name="self-hosted")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    endpoint(
        "endpoint",
        "Where your Grafana answers, scheme and port included — "
        "http://grafana.example.com:3000. The same address you sign in at.",
        label="Grafana address",
        guide_url="https://grafana.com/docs/grafana/latest/setup-grafana/",
    ),
    secret(
        "token",
        "Grafana service account token, with the Viewer role at minimum",
        min_length=8,
        label="Service account token",
        min_scope="Viewer role",
        guide_url="https://grafana.com/docs/grafana/latest/administration/service-accounts/",
    ),
    public(
        "org",
        "Grafana organisation id, when the stack has more than one",
        label="Organisation ID",
        guide_url="https://grafana.com/docs/grafana/latest/administration/organization-management/",
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(BearerTokenInjection(field="token"),),
)


def base_url(region: str = "") -> str:
    """Return the API base URL for a region, or for the default one."""
    return REGIONS.base_url(region)


def rule_for(*hosts: str) -> InjectionRule:
    """Return the injection rule permitting the endpoints a deployment configured.

    Grafana is self-hosted, so nobody writing this file knows where it is.
    The allow-list is still declared and still enforced; the declaration is just
    made by the operator. The documented default is always permitted, because a
    deployment that configured one endpoint may still reach the other.
    """
    return InjectionRule(
        integration=INTEGRATION,
        hosts=tuple(sorted({DEFAULT_HOST, *hosts})),
        injections=RULE.injections,
    )


def regions_for(**endpoints: str) -> RegionMap:
    """Return the region map for the endpoints a deployment configured.

    Keyword arguments are the name an operator selects by, mapped to the host —
    ``regions_for(prod="grafana.acme.example")``.
    """
    named = {"self-hosted": DEFAULT_HOST, **endpoints}
    return RegionMap(
        integration=INTEGRATION,
        regions=tuple(Region(name=name, host=host) for name, host in named.items()),
        default="self-hosted",
    )


__all__ = [
    "DEFAULT_HOST",
    "HOSTS",
    "INTEGRATION",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "base_url",
    "regions_for",
    "rule_for",
]
