"""Proxmox credentials, the two ways it authenticates, and where it can be reached.

Three declarations, and Proxmox makes each of them slightly awkward.

**The host is not knowable in advance.** A hypervisor is somebody's own machine
on somebody's own network, so nobody writing this file can write the egress
allow-list. ``rule_for`` builds it from the addresses a deployment actually
configured — the same declaration ``regions_for`` reads, so the catalogue and the
allow-list cannot drift apart. The documented default is the placeholder an
operator replaces, and it is permitted so that a deployment that configured one
endpoint can still be pointed at the other.

**The API listens on 8006, not 443.** The port is part of the URL and not part of
the allow-list: ``InjectionRule`` refuses a ``host:port`` entry, correctly, since
a port is not a security boundary and a list with one in it is wrong the first
time a vendor moves. ``base_url`` puts the port back on the request.

**There are two ways in, and they are not equally good.** An API token is a
header — ``Authorization: PVEAPIToken=USER@REALM!TOKENID=SECRET`` — which is
exactly the shape a declared injection covers, so the proxy adds it and no
Proxmox code ever sees it. A ticket is a login: username and password exchanged
for a two-hour cookie and a CSRF token. That exchange *is* an authenticated call,
so it happens on the proxy side through ``ProxmoxTicketRefresher`` and the rule
declares itself refreshable; a client that could exchange a ticket would hold the
password, which is a longer-lived secret than the thing it buys.

An operator who can issue a token should. The ticket path exists because some
deployments — an old realm, a directory-backed login, a cluster whose token
creation is locked down — cannot, and refusing them would be refusing the
deployment rather than the credential.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, endpoint, public, secret
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule

INTEGRATION: Final = "proxmox"

#: The port a Proxmox node serves its API on. Fixed by the vendor, and separate
#: from the allow-list for the reason the module docstring gives.
API_PORT: Final = 8006

#: Every path below is relative to this. Proxmox's other prefixes — ``api2/extjs``
#: and ``api2/html`` — answer the same routes in shapes meant for its own web
#: interface, and reading those would couple this client to a console.
API_BASE: Final = "/api2/json"

#: The placeholder host, which an operator replaces with their own. Permitted by
#: every rule for the same reason Grafana's is: a deployment that configured one
#: endpoint may still be pointed at the documented one.
DEFAULT_HOST: Final = "proxmox.example.com"

#: NFR-005, and the only place it is written. Everything that reports which
#: Proxmox versions this integration is tested against reads this tuple; a second
#: statement of it is a second thing to forget on an upgrade.
TESTED_VERSIONS: Final[tuple[str, ...]] = ("8.4", "9.2")

#: The major versions whose API surface this client is written against. Proxmox
#: changed neither the paths nor the envelope between 8 and 9, and the reference
#: cluster runs 9.2.6.
SUPPORTED_MAJORS: Final[tuple[str, ...]] = ("8", "9")

#: What a Proxmox API token id and secret look like joined the way the vendor's
#: own documentation joins them: ``user@realm!tokenid=secret``. Worth pinning
#: because the commonest setup mistake is pasting the secret alone, which
#: produces a 401 that reads like a revoked token.
API_TOKEN_PATTERN: Final = r"[A-Za-z0-9_.\-]+@[A-Za-z0-9_.\-]+![A-Za-z0-9_\-]+=[A-Za-z0-9\-]+"

#: Proxmox has no vendor regions. The "region" an operator selects is which
#: cluster they mean, and the map is built from what they configured.
REGIONS: Final = RegionMap.single(INTEGRATION, host=DEFAULT_HOST, name="self-hosted")

#: The egress allow-list, which is the region map rather than a second tuple.
HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    endpoint(
        "endpoint",
        "Where a node of your cluster answers, port included — "
        "https://proxmox.example.com:8006. Any node will do: the API answers cluster-"
        "wide questions from whichever one is asked.",
        label="Proxmox node address",
    ),
    secret(
        "api_token",
        "Proxmox API token as one line, exactly as the header wants it: "
        "user@realm!tokenid=secret. Privilege separation is a property of the "
        "token rather than of this field — a separated token sends identically "
        "and simply holds fewer privileges, which verification reports.",
        pattern=API_TOKEN_PATTERN,
        alternatives=("password",),
        label="API token",
        min_scope=(
            "Sys.Audit on /, VM.Audit on /vms and Datastore.Audit on /storage — "
            "granted together by the PVEAuditor role on /"
        ),
        guide_url="https://pve.proxmox.com/pve-docs/chapter-pveum.html",
    ),
    public(
        "username",
        "Login name with its realm, such as ninjasre@pve. Only for deployments "
        "that cannot issue an API token.",
        label="Login name",
    ),
    secret(
        "password",
        "Password for the ticket login. Exchanged for a two-hour ticket on the "
        "proxy side and never read here.",
        required=False,
        alternatives=("api_token",),
        label="Password",
    ),
    secret(
        "ticket",
        "The short-lived ticket the proxy exchanged the password for. Written by "
        "the refresher, never by an operator.",
        required=False,
        label="Session ticket",
    ),
    secret(
        "csrf_token",
        "The CSRF prevention token that accompanies a ticket. Written by the "
        "refresher, never by an operator.",
        required=False,
        label="CSRF token",
    ),
)

#: How an API token enters the request. One header, in Proxmox's own format.
TOKEN_INJECTIONS: Final = (
    HeaderInjection(header="Authorization", field="api_token", template="PVEAPIToken={value}"),
)

#: How a ticket enters the request: the cookie Proxmox sets at login, plus the
#: CSRF token it expects alongside it. Both are refreshed values, which is why
#: the rule that carries them declares itself refreshable.
TICKET_INJECTIONS: Final = (
    HeaderInjection(header="Cookie", field="ticket", template="PVEAuthCookie={value}"),
    HeaderInjection(header="CSRFPreventionToken", field="csrf_token"),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=TOKEN_INJECTIONS,
)


def rule_for(*hosts: str) -> InjectionRule:
    """Return the token injection rule permitting the endpoints a deployment configured.

    Every node's address belongs here, not only the one named in the
    configuration: failing over to a surviving node is the whole point of
    accepting several, and an allow-list one entry short turns that into a
    refusal at exactly the moment it was meant to help.
    """
    return InjectionRule(
        integration=INTEGRATION,
        hosts=tuple(sorted({DEFAULT_HOST, *hosts})),
        injections=TOKEN_INJECTIONS,
    )


def ticket_rule_for(*hosts: str) -> InjectionRule:
    """Return the ticket injection rule for a deployment that cannot issue tokens.

    ``refreshable`` is what turns on the proxy's refresh-before-expiry and its
    single retry after an expiry-shaped rejection. A Proxmox ticket lasts two
    hours, so without it every deployment on this path would fail one call in
    every hour and recover by accident.
    """
    return InjectionRule(
        integration=INTEGRATION,
        hosts=tuple(sorted({DEFAULT_HOST, *hosts})),
        injections=TICKET_INJECTIONS,
        refreshable=True,
    )


def regions_for(**clusters: str) -> RegionMap:
    """Return the cluster map for the endpoints a deployment configured.

    Keyword arguments are the name an operator selects by, mapped to a host:
    ``regions_for(hal9000="pve01.acme.example")``.
    """
    named = {"self-hosted": DEFAULT_HOST, **clusters}
    return RegionMap(
        integration=INTEGRATION,
        regions=tuple(Region(name=name, host=host) for name, host in named.items()),
        default="self-hosted",
    )


def base_url(host: str = DEFAULT_HOST) -> str:
    """Return the API base URL for one Proxmox node's address."""
    return f"https://{host}:{API_PORT}{API_BASE}"


def tested_versions_note() -> str:
    """Return the sentence that states which Proxmox versions this is tested against."""
    return (
        f"Tested against Proxmox VE {' and '.join(TESTED_VERSIONS)}; written against the "
        f"{' and '.join(SUPPORTED_MAJORS)} major series, whose API paths are identical."
    )


__all__ = [
    "API_BASE",
    "API_PORT",
    "API_TOKEN_PATTERN",
    "DEFAULT_HOST",
    "HOSTS",
    "INTEGRATION",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "SUPPORTED_MAJORS",
    "TESTED_VERSIONS",
    "TICKET_INJECTIONS",
    "TOKEN_INJECTIONS",
    "base_url",
    "regions_for",
    "rule_for",
    "tested_versions_note",
    "ticket_rule_for",
]
