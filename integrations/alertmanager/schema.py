"""Alertmanager's credential shape, hosts, and how its secret enters a request.

Three declarations, each preventing one failure. The schema is what an operator
is prompted for, and a field they were never asked for is a credential that half
works. The region map is the egress allow-list — one tuple rather than two,
because two drift. The injection rule is how the secret is added at the network
edge, and every field it reads is one the schema declares.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, endpoint, secret
from platform.credentials.proxy.injection import BearerTokenInjection, InjectionRule

INTEGRATION: Final = "alertmanager"


#: Where a default install serves its API. See ``rule_for``.
DEFAULT_HOST: Final = "alertmanager.example.com"

#: Every host Alertmanager serves its API from. Exact names, no wildcards.
REGIONS: Final = RegionMap.single(INTEGRATION, host="alertmanager.example.com", name="self-hosted")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    endpoint(
        "endpoint",
        "Where your Alertmanager answers, scheme and port included — "
        "http://alertmanager.example.com:9093. Nobody packaging this knows where "
        "yours is, so until it is declared every call goes to the documented "
        "placeholder.",
        label="Alertmanager address",
        guide_url="https://prometheus.io/docs/alerting/latest/alertmanager/",
    ),
    secret(
        "token",
        "Only if something in front of Alertmanager asks for one. Alertmanager "
        "ships no authentication of its own, so an install reached directly "
        "needs nothing here.",
        min_length=8,
        required=False,
        label="Bearer token",
        min_scope="whatever your reverse proxy or ingress accepts",
        guide_url="https://prometheus.io/docs/guides/basic-auth/",
    ),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(BearerTokenInjection(field="token"),),
    # Alertmanager ships no authentication. Requiring one made the ordinary
    # install — bare, on a private address, behind nothing — the one shape this
    # integration could not be connected to.
    credential_optional=True,
)


def base_url(region: str = "") -> str:
    """Return the API base URL for a region, or for the default one."""
    return REGIONS.base_url(region)


def rule_for(*hosts: str) -> InjectionRule:
    """Return the injection rule permitting the endpoints a deployment configured.

    Alertmanager is self-hosted, so nobody writing this file knows where it is.
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
    ``regions_for(prod="alertmanager.acme.example")``.
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
