"""Proxmox VE: the hypervisor a self-hoster actually runs, read end to end.

The two declarations every vendor package exposes, and one thing most of them do
not: a discovery source. Proxmox is the first integration to implement feature
038's protocol, because a hypervisor is the case the estate was designed around —
a cluster, its nodes, its guests, its datastores, and the parentage between them
all come from one provider that already knows the whole shape.

``DESCRIPTOR`` carries the API-token rule against the documented placeholder
host. A deployment replaces it at composition with ``schema.rule_for(...)`` over
its own nodes' addresses, and the proxy enforces whichever it was given —
Proxmox is somebody's own machine on somebody's own network, so the allow-list
is declared by the operator rather than by NinjaSRE.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.proxmox.certificates import CertificateTrust, UnverifiedTransportRefused
from integrations.proxmox.client import PAGINATION, ProxmoxClient
from integrations.proxmox.discovery import PROXMOX_KINDS, ProxmoxDiscovery
from integrations.proxmox.endpoints import EndpointRing, NoEndpointReachable
from integrations.proxmox.schema import (
    DEFAULT_HOST,
    INTEGRATION,
    REGIONS,
    RULE,
    SCHEMA,
    TESTED_VERSIONS,
    base_url,
    regions_for,
    rule_for,
    ticket_rule_for,
)
from integrations.proxmox.verifier import PERMISSIONS, ProxmoxVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

PROXMOX: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=ProxmoxVerifier(),
    client_class=ProxmoxClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "Every Proxmox client library loads its own credential — from a constructor "
        "argument, a configuration file, or the environment — which is the behaviour "
        "Article IV forbids and the one thing about such a library that is never "
        "configurable away. The reads an investigation needs are a bounded set of REST "
        "paths, so a direct client on the proxy transport costs less than the adaptation "
        "would and holds nothing."
    ),
)

DESCRIPTOR: Final = PROXMOX

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary=(
        "A Proxmox VE cluster read whole: quorum, nodes, containers, virtual machines, "
        "datastores, thin pools, backups and replication, at whichever addresses the "
        "operator declared."
    ),
    regions=REGIONS,
    permissions=PERMISSIONS,
    pagination=PAGINATION,
)

__all__ = [
    "DEFAULT_HOST",
    "DESCRIPTOR",
    "INTEGRATION",
    "PAGINATION",
    "PERMISSIONS",
    "PROFILE",
    "PROXMOX",
    "PROXMOX_KINDS",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "TESTED_VERSIONS",
    "CertificateTrust",
    "EndpointRing",
    "NoEndpointReachable",
    "ProxmoxClient",
    "ProxmoxDiscovery",
    "ProxmoxVerifier",
    "UnverifiedTransportRefused",
    "base_url",
    "regions_for",
    "rule_for",
    "ticket_rule_for",
]
