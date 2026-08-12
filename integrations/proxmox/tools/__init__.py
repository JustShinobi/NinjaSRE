"""Proxmox's agent-callable capabilities, in the order an investigation asks them.

A hypervisor fails from the top down and is investigated the same way, because
the failures at the top invalidate everything below them: a cluster without
quorum cannot start a guest, so "the guest will not start" has already been
answered before anybody looks at the guest.

**The cluster, first and always.**

- ``proxmox_cluster_health`` — quorum, votes, and which nodes are answering.
- ``proxmox_quorum_status`` — the same arithmetic with the corosync settings
  behind it and the consequences that follow from losing it.
- ``proxmox_corosync_links`` — flapping told from lost, and a ring that can
  never come up.
- ``proxmox_ha_state`` — what is managed, and whether fencing is imminent.
- ``proxmox_clock_skew`` — measured against what corosync tolerates.
- ``proxmox_node_health`` — failed systemd units, bridge state, and thin-pool
  metadata, none of which the Proxmox API answers.

**Then storage, at the level that is actually failing.**

- ``proxmox_storage_pressure`` — datastores, thin pools, and the guests near
  their own ceiling, which a datastore-level threshold cannot see.
- ``proxmox_zfs_health``, ``proxmox_disk_health`` — pools and the drives beneath
  them, including the attributes that predict a failure the verdict does not.
- ``proxmox_reclaimable_space`` — what could be freed and what each item is
  protecting, never one without the other.
- ``proxmox_orphaned_volumes``, ``proxmox_datastore_availability``.

**Then the guest, once the two above are ruled in or out.**

- ``proxmox_guest_start_diagnosis``, ``proxmox_guest_pressure``,
  ``proxmox_guest_tasks``, ``proxmox_migration_feasibility``.

**And recovery, which is a different question from health.**

- ``proxmox_protection_gaps``, ``proxmox_backup_coverage``,
  ``proxmox_backup_failures``, ``proxmox_replication_lag``.

Nothing here writes. Starting, stopping, migrating and backing up a guest are
remediations that need an approval and a rollback plan, and putting one in this
package would leave it one typo away from being called by something that thought
it was reading.
"""

from __future__ import annotations

from integrations.proxmox.tools.backup_coverage import proxmox_backup_coverage
from integrations.proxmox.tools.backup_failures import proxmox_backup_failures
from integrations.proxmox.tools.clock_skew import proxmox_clock_skew
from integrations.proxmox.tools.cluster_health import proxmox_cluster_health
from integrations.proxmox.tools.corosync_links import proxmox_corosync_links
from integrations.proxmox.tools.datastore_availability import proxmox_datastore_availability
from integrations.proxmox.tools.disk_health import proxmox_disk_health
from integrations.proxmox.tools.guest_pressure import proxmox_guest_pressure
from integrations.proxmox.tools.guest_start_diagnosis import proxmox_guest_start_diagnosis
from integrations.proxmox.tools.guest_tasks import proxmox_guest_tasks
from integrations.proxmox.tools.ha_state import proxmox_ha_state
from integrations.proxmox.tools.migration_feasibility import proxmox_migration_feasibility
from integrations.proxmox.tools.node_health import proxmox_node_health
from integrations.proxmox.tools.orphaned_volumes import proxmox_orphaned_volumes
from integrations.proxmox.tools.protection_gaps import proxmox_protection_gaps
from integrations.proxmox.tools.quorum_status import proxmox_quorum_status
from integrations.proxmox.tools.reclaimable_space import proxmox_reclaimable_space
from integrations.proxmox.tools.replication_lag import proxmox_replication_lag
from integrations.proxmox.tools.storage_pressure import proxmox_storage_pressure
from integrations.proxmox.tools.zfs_health import proxmox_zfs_health

__all__ = [
    "proxmox_backup_coverage",
    "proxmox_backup_failures",
    "proxmox_clock_skew",
    "proxmox_cluster_health",
    "proxmox_corosync_links",
    "proxmox_datastore_availability",
    "proxmox_disk_health",
    "proxmox_guest_pressure",
    "proxmox_guest_start_diagnosis",
    "proxmox_guest_tasks",
    "proxmox_ha_state",
    "proxmox_migration_feasibility",
    "proxmox_node_health",
    "proxmox_orphaned_volumes",
    "proxmox_protection_gaps",
    "proxmox_quorum_status",
    "proxmox_reclaimable_space",
    "proxmox_replication_lag",
    "proxmox_storage_pressure",
    "proxmox_zfs_health",
]
