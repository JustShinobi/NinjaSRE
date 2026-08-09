"""Proxmox Backup Server's credential, which is deliberately not Proxmox VE's.

A separate integration rather than a mode of the hypervisor one, and the reason
is the whole point of the separation: **Proxmox Backup Server is usually a
different machine.** It is the machine that has to survive the cluster, and a
deployment that reached it with the cluster's credential would have a backup
server that stops being readable at exactly the moment the cluster does.

So it has its own host, its own token, its own egress allow-list, and its own
verification. An operator configures two integrations, which is one more setup
step and one fewer shared fate.

The token format differs too, and the difference is easy to miss because it is one
character: Proxmox VE joins the token id and the secret with ``=``, and Backup
Server joins them with ``:``. A token pasted into the wrong integration
authenticates against neither.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from integrations._base.schema import credential_schema, public, secret
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule

INTEGRATION: Final = "proxmox_backup_server"

#: Where a Backup Server serves its API. One port along from the hypervisor's.
API_PORT: Final = 8007

API_BASE: Final = "/api2/json"

#: The placeholder host an operator replaces with their own.
DEFAULT_HOST: Final = "backup.example.com"

#: NFR-005 for this half of the wave: the versions this client is tested against.
TESTED_VERSIONS: Final[tuple[str, ...]] = ("3.4", "4.0")

#: ``user@realm!tokenid:secret`` — note the colon, which is where this differs
#: from Proxmox VE and which is the commonest reason a correctly-issued Backup
#: Server token fails to authenticate.
API_TOKEN_PATTERN: Final = r"[A-Za-z0-9_.\-]+@[A-Za-z0-9_.\-]+![A-Za-z0-9_\-]+:[A-Za-z0-9\-]+"

REGIONS: Final = RegionMap.single(INTEGRATION, host=DEFAULT_HOST, name="self-hosted")

HOSTS: Final[tuple[str, ...]] = REGIONS.hosts()

SCHEMA: Final = credential_schema(
    INTEGRATION,
    secret(
        "api_token",
        "Backup Server API token as one line: user@realm!tokenid:secret. The separator "
        "is a colon here and an equals sign in Proxmox VE; a token pasted into the wrong "
        "integration authenticates against neither.",
        pattern=API_TOKEN_PATTERN,
    ),
    public("fingerprint", "SHA-256 fingerprint of the server's certificate, when it is pinned"),
)

RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=HOSTS,
    injections=(
        HeaderInjection(header="Authorization", field="api_token", template="PBSAPIToken={value}"),
    ),
)


def rule_for(*hosts: str) -> InjectionRule:
    """Return the injection rule permitting the Backup Servers a deployment configured."""
    return InjectionRule(
        integration=INTEGRATION,
        hosts=tuple(sorted({DEFAULT_HOST, *hosts})),
        injections=RULE.injections,
    )


def regions_for(**servers: str) -> RegionMap:
    """Return the map for the Backup Servers a deployment configured."""
    named = {"self-hosted": DEFAULT_HOST, **servers}
    return RegionMap(
        integration=INTEGRATION,
        regions=tuple(Region(name=name, host=host) for name, host in named.items()),
        default="self-hosted",
    )


def base_url(host: str = DEFAULT_HOST) -> str:
    """Return the API base URL for one Backup Server."""
    return f"https://{host}:{API_PORT}{API_BASE}"


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
    "TESTED_VERSIONS",
    "base_url",
    "regions_for",
    "rule_for",
]
