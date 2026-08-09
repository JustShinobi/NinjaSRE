"""The bounds a hypervisor write obeys: waiting, settling, collisions, caps.

Separate from the closed-loop constants because these are facts about a
hypervisor rather than about verification. How long a guest's operating system
takes to close its files is not a preference an operator holds, and neither is
how close to a scheduled backup another backup counts as a collision.

Three of them decide whether an action is safe rather than how long it takes,
and those are the ones worth reading before changing.
"""

from __future__ import annotations

from typing import Final

# --- Waiting for a guest ------------------------------------------------------

#: How long a graceful guest shutdown is given before Proxmox itself gives up.
#: Ten minutes: a database flushing a large buffer pool routinely takes minutes,
#: and a guest that shuts down cleanly but slowly must not be hard-stopped for
#: being slow. This is passed to Proxmox as the request's own timeout.
GUEST_SHUTDOWN_TIMEOUT_SECONDS: Final[int] = 600

#: How long after a graceful shutdown was asked for a restart may escalate to a
#: hard stop. Longer than the shutdown timeout on purpose: the escalation is only
#: correct once Proxmox has reported the graceful attempt finished without the
#: guest stopping, and a shorter window would race the attempt it is waiting on.
HARD_STOP_ESCALATION_SECONDS: Final[int] = 900

# --- Settling -----------------------------------------------------------------

#: How long before a guest's own state is worth reading back. Long enough for a
#: container to finish starting its services, short enough that an operator
#: watching an incident does not conclude nothing happened.
GUEST_SETTLE_SECONDS: Final[int] = 120

#: How long before a migrated guest is worth reading back. A memory copy over a
#: domestic link takes longer than any local operation on this list.
MIGRATION_SETTLE_SECONDS: Final[int] = 600

#: How long before a datastore reflects a deletion. LVM-thin returns extents to
#: the pool lazily and a share reports its own free space on its own schedule.
STORAGE_SETTLE_SECONDS: Final[int] = 300

#: How long before a backup's outcome is worth reading. A full backup of a large
#: guest outlives this; the obligation is re-read rather than the wait extended.
BACKUP_SETTLE_SECONDS: Final[int] = 1800

#: How long before a replication job's lag is worth reading back.
REPLICATION_SETTLE_SECONDS: Final[int] = 900

# --- Collisions and caps ------------------------------------------------------

#: How close to a scheduled backup run another backup counts as colliding with
#: it. One hour: two vzdump runs against one guest contend for the same lock and
#: the same datastore, and the scheduled one is the one somebody depends on.
BACKUP_COLLISION_WINDOW_SECONDS: Final[int] = 3600

#: The rate a replication resync is limited to unless an operator names another,
#: in megabytes per second. Corosync shares the link a resync saturates, and a
#: cluster that loses its membership layer to a storage sync has traded a lagging
#: replica for an unquorate cluster.
DEFAULT_REPLICATION_RATE_LIMIT_MBPS: Final[int] = 50

#: How many items one reclamation may name. A list rather than a policy is the
#: whole design, and a list long enough to be unreadable is a policy again.
MAX_RECLAIMED_ITEMS: Final[int] = 25

#: How many nodes a cluster may have before "one member is unreachable" stops
#: being an ambiguity a vote cannot resolve. At two, losing one leaves the
#: survivor unable to tell a dead peer from an unreachable one.
QUORUM_AMBIGUITY_NODE_COUNT: Final[int] = 2

__all__ = [
    "BACKUP_COLLISION_WINDOW_SECONDS",
    "BACKUP_SETTLE_SECONDS",
    "DEFAULT_REPLICATION_RATE_LIMIT_MBPS",
    "GUEST_SETTLE_SECONDS",
    "GUEST_SHUTDOWN_TIMEOUT_SECONDS",
    "HARD_STOP_ESCALATION_SECONDS",
    "MAX_RECLAIMED_ITEMS",
    "MIGRATION_SETTLE_SECONDS",
    "QUORUM_AMBIGUITY_NODE_COUNT",
    "REPLICATION_SETTLE_SECONDS",
    "STORAGE_SETTLE_SECONDS",
]
