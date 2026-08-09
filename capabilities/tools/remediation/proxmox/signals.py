"""The signals a hypervisor write's effect appears in, named once.

Thirteen declarations naming the same six signals as string literals is six
chances for one of them to be spelled differently, and a capability that names a
signal nothing produces verifies against nothing for ever while reporting
``inconclusive`` — which reads exactly like a system whose effects are hard to
measure and is not.

So the names live here, and a deployment wiring observation reads one list. The
thresholds beside each one are the value at which the condition an action was
taken against no longer holds; where a capability cannot name one, it says so by
leaving it out, and pays for it with an ``inconclusive`` rather than an
``ineffective`` on a small move.
"""

from __future__ import annotations

from typing import Final

#: Whether the guest is running, as one and zero. Up is better: a start worked
#: when the guest is running, and the clearing value is exactly one.
GUEST_RUNNING: Final = "proxmox.guest.running"

#: Whether the guest carries a lock. Down is better, and cleared at zero.
GUEST_LOCKED: Final = "proxmox.guest.locked"

#: How often a guest has restarted in the last hour. One an hour is the
#: deployment's own doing; more than that is the guest failing again.
GUEST_RESTARTS_PER_HOUR: Final = "proxmox.guest.restarts_per_hour"

#: How much of a node's memory is committed, as a percentage. What a shutdown, a
#: suspend, a hard stop and a migration are usually taken against.
NODE_MEMORY_PERCENT: Final = "proxmox.node.memory_percent"

#: How full a datastore is, as a percentage. What a reclamation moves.
DATASTORE_USED_PERCENT: Final = "proxmox.datastore.used_percent"

#: How far behind a replication target is, in seconds.
REPLICATION_LAG_SECONDS: Final = "proxmox.replication.lag_seconds"

#: How old a guest's most recent successful backup is, in hours.
BACKUP_AGE_HOURS: Final = "proxmox.backup.age_hours"

#: Every signal this feature's capabilities read. One list, so an operator
#: wiring observation has something to check their sources against.
HYPERVISOR_SIGNALS: Final[tuple[str, ...]] = (
    BACKUP_AGE_HOURS,
    DATASTORE_USED_PERCENT,
    GUEST_LOCKED,
    GUEST_RESTARTS_PER_HOUR,
    GUEST_RUNNING,
    NODE_MEMORY_PERCENT,
    REPLICATION_LAG_SECONDS,
)

__all__ = [
    "BACKUP_AGE_HOURS",
    "DATASTORE_USED_PERCENT",
    "GUEST_LOCKED",
    "GUEST_RESTARTS_PER_HOUR",
    "GUEST_RUNNING",
    "HYPERVISOR_SIGNALS",
    "NODE_MEMORY_PERCENT",
    "REPLICATION_LAG_SECONDS",
]
