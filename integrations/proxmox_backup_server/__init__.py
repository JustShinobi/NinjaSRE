"""Proxmox Backup Server: the machine that has to survive the cluster.

A separate integration from Proxmox VE, with its own host, its own token and its
own verification, because it is usually a separate machine — and one that is
reached with the cluster's credential stops being readable at exactly the moment
the cluster does.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.proxmox_backup_server.client import PAGINATION, ProxmoxBackupServerClient
from integrations.proxmox_backup_server.schema import (
    DEFAULT_HOST,
    INTEGRATION,
    REGIONS,
    RULE,
    SCHEMA,
    TESTED_VERSIONS,
    base_url,
    regions_for,
    rule_for,
)
from integrations.proxmox_backup_server.verifier import (
    PERMISSIONS,
    ProxmoxBackupServerVerifier,
)
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

PROXMOX_BACKUP_SERVER: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=ProxmoxBackupServerVerifier(),
    client_class=ProxmoxBackupServerClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "Proxmox publishes no Python client for Backup Server, and the community ones load "
        "a credential themselves, which Article IV forbids. The reads an investigation "
        "needs are four REST paths on the shared client base."
    ),
)

DESCRIPTOR: Final = PROXMOX_BACKUP_SERVER

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Proxmox Backup Server",
    category=IntegrationCategory.CLOUD_CONTROL_PLANE,
    summary=(
        "Datastore usage, snapshots, verification outcomes and garbage-collection state "
        "from a Proxmox Backup Server, at whichever address the operator declared."
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
    "PROXMOX_BACKUP_SERVER",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "TESTED_VERSIONS",
    "ProxmoxBackupServerClient",
    "ProxmoxBackupServerVerifier",
    "base_url",
    "regions_for",
    "rule_for",
]
