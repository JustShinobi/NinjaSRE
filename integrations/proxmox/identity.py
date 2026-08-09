"""What a Proxmox thing *is*, in a way that survives being renamed and moved.

An identity that is wrong in either direction is expensive. Too unstable and
every rename produces a new resource, so six months of a guest's health history
ends the day somebody corrects a typo in its hostname. Too stable and a VMID
reused after a guest was destroyed inherits the dead guest's history, which is
worse: the estate reports continuity that does not exist, and a detector reading
"this guest has been degraded for a week" is reading about something that no
longer exists.

The rules that follow from that:

**The node is never part of a guest's identity.** Migration is a normal
operation, and a guest that changed identity on migration would be a guest whose
history restarts every time the cluster balances itself. The node is the
*parent*, which is where a change belongs.

**The name is never part of anything's identity.** Renaming is what an operator
does when they realise the name is wrong.

**A guest's identity carries when it was created.** Proxmox writes ``meta:
creation-lxc=…,ctime=…`` into a guest's configuration at creation and never
touches it again, so it is the one field that distinguishes VMID 100 from the
VMID 100 that came before it. Where it is genuinely absent the identity falls
back to the VMID alone and the resource carries a signal saying so — an invented
discriminator would be worse than a missing one, because it would make every
sweep produce a brand-new resource.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: What a guest's identity says when the provider gave no creation time. Written
#: into the identity rather than omitted, so that a guest whose configuration
#: later gains the field is visibly a different identity rather than silently one.
NO_DISCRIMINATOR: Final = "unknown"


def cluster_identity(cluster: str) -> str:
    """Return the identity of a cluster, by the name corosync knows it by."""
    return f"cluster/{cluster}"


def node_identity(cluster: str, node: str) -> str:
    """Return a node's identity.

    The node's own name *is* its identity here, unlike a guest's: renaming a
    Proxmox node is not an operation — it requires removing it from the cluster
    and adding it back, which is a new node in every sense that matters.
    """
    return f"node/{cluster}/{node}"


def guest_identity(cluster: str, kind: str, vmid: int, *, created_at: str) -> str:
    """Return a guest's identity: cluster, kind, VMID, and when it was created."""
    return f"{kind}/{cluster}/{created_at or NO_DISCRIMINATOR}/{vmid}"


def datastore_identity(cluster: str, node: str, datastore: str) -> str:
    """Return a datastore's identity as one node sees it.

    Scoped to the node on purpose. A share visible from one node and not another
    is exactly the reference cluster's state, and one record for a datastore
    would have to choose which node's view to believe.
    """
    return f"datastore/{cluster}/{node}/{datastore}"


def pool_identity(cluster: str, node: str, volume_group: str, pool: str) -> str:
    """Return a thin pool's identity, which is its volume group and its name."""
    return f"pool/{cluster}/{node}/{volume_group}/{pool}"


def disk_identity(cluster: str, node: str, serial: str, device: str) -> str:
    """Return a physical disk's identity.

    The serial number when there is one, because a disk moved to another bay
    keeps its serial and changes its device path — and a disk that changed
    identity on being re-cabled would lose its SMART history at the moment it
    was being investigated.
    """
    return f"disk/{cluster}/{node}/{serial or device}"


def backup_job_identity(cluster: str, job_id: str) -> str:
    """Return a backup job's identity, which Proxmox already assigns."""
    return f"backupjob/{cluster}/{job_id}"


def replication_job_identity(cluster: str, job_id: str) -> str:
    """Return a replication job's identity, which Proxmox already assigns."""
    return f"replication/{cluster}/{job_id}"


def creation_time(configuration: Mapping[str, Any]) -> str:
    """Return when a guest was created, from its configuration's own metadata.

    Proxmox packs it into ``meta`` as ``creation-<kind>=<version>,ctime=<epoch>``.
    Returns the empty string when the key is absent, which is a real answer: a
    guest created by an older Proxmox, or restored from a backup taken by one,
    genuinely has no recorded creation time and the caller must say so rather
    than substitute something.
    """
    meta = str(configuration.get("meta", ""))
    for part in meta.split(","):
        name, _, value = part.partition("=")
        if name.strip() == "ctime" and value.strip().isdigit():
            return value.strip()
    return ""


def correlation_key(node: str, serial: str = "") -> str:
    """Return what another integration describing the same machine would also report.

    A disk's serial, or a node's fully-qualified name. Empty when there is
    nothing another source could match on — and reconciliation never matches
    empty against empty, because the absence of a correlator is not one.
    """
    return serial or node


__all__ = [
    "NO_DISCRIMINATOR",
    "backup_job_identity",
    "cluster_identity",
    "correlation_key",
    "creation_time",
    "datastore_identity",
    "disk_identity",
    "guest_identity",
    "node_identity",
    "pool_identity",
    "replication_job_identity",
]
