"""Proxmox's agent-callable capabilities: three reads, in the order they matter.

A hypervisor investigation starts at the cluster and works down, because the
failures at the top invalidate everything below them: a cluster without quorum
cannot start a guest, so "the guest will not start" has already been answered
before anybody looks at the guest.

- ``proxmox_cluster_health`` — quorum, votes, and which nodes are answering.
- ``proxmox_storage_pressure`` — datastores, thin pools, and the guests near
  their own ceiling, which a datastore-level threshold cannot see.
- ``proxmox_protection_gaps`` — which guests are covered by an *enabled* backup
  job and whether anything is replicated.

Nothing here writes. Starting, stopping, migrating and backing up a guest are
remediations that need an approval and a rollback plan, and putting one in this
package would leave it one typo away from being called by something that thought
it was reading.
"""

from __future__ import annotations

from integrations.proxmox.tools.cluster_health import proxmox_cluster_health
from integrations.proxmox.tools.protection_gaps import proxmox_protection_gaps
from integrations.proxmox.tools.storage_pressure import proxmox_storage_pressure

__all__ = [
    "proxmox_cluster_health",
    "proxmox_protection_gaps",
    "proxmox_storage_pressure",
]
