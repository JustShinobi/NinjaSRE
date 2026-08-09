"""The risk table for every write this deployment may make to a hypervisor.

One module, reviewable as a whole, and asserted against the registry so the
document an operator reads is the one the system obeys. A class scattered across
thirteen capability modules is a classification nobody has ever read.

**A class is the worst answer to four questions.** Can it be undone; how far does
it reach; can it lose data; can it lose availability. Each row states all four in
prose, because "moderate" tells a reviewer nothing and "undone by starting the
guest again, and its in-flight writes are gone" tells them everything.

**Data loss dominates size.** A hundred-megabyte snapshot that is the only recent
recovery point is a more dangerous deletion than a fifty-gigabyte orphaned disk.
``RiskRow`` refuses to be constructed with ``loses_data`` below the top of the
scale, so the rule is enforced where the table is written rather than checked
somewhere a later row could miss.

**The three bands of the specification map onto five classes.** The lowest band
is ``trivial`` and ``low`` — everything at or below the default risk bound, which
is what "may run unattended under the ordinary posture" means operationally. The
middle band is ``moderate``. The highest is ``high`` and ``critical``, and the
difference between them is whether data with no other copy can go.

**The prohibitions are part of the table.** They are the deliberate hole: no
capability may fence a node, force quorum, alter corosync, restart a node's own
services, or write a node's network configuration. Declaring them here as paths
is what lets one test sweep the whole registry rather than a list somebody
maintains, so a capability in a prohibited category fails the suite rather than
shipping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from platform.autonomy.risk import RiskClass

#: The datastore content kinds that exist to get something back. Anything in this
#: set is a recovery point, and deleting one is the top of the scale whatever it
#: weighs. ``replication-base`` is the last common snapshot a replication job
#: resumes from: removing it does not delete a guest and does turn the next
#: incremental sync into a full one, over a link that may not have room for it.
RECOVERY_POINT_CONTENT: Final[tuple[str, ...]] = ("backup", "snapshot", "replication-base")


@dataclass(frozen=True, slots=True)
class RiskRow:
    """One action's classification, and the reasoning a reviewer checks it against."""

    capability: str
    risk_class: RiskClass
    reversibility: str
    data_loss: str
    availability: str
    blast_radius: str
    #: Whether this action can destroy something that has no other copy. Kept
    #: separate from the prose because it is the one answer a test can assert on,
    #: and because it is the one that fixes the class rather than informing it.
    loses_data: bool = False

    def __post_init__(self) -> None:
        for name in ("capability", "reversibility", "data_loss", "availability", "blast_radius"):
            if not str(getattr(self, name)).strip():
                raise ValueError(
                    f"{self.capability or 'a risk row'}: {name} is blank, so this row classifies "
                    f"an action nobody assessed on that axis."
                )
        if self.loses_data and self.risk_class is not RiskClass.CRITICAL:
            raise ValueError(
                f"{self.capability} loses data and is classified {self.risk_class.value}. An "
                f"action that can destroy something with no other copy is the top of the scale "
                f"however small the change is."
            )

    def describe(self) -> str:
        """Return the row as the single line a review reads."""
        return (
            f"{self.capability} [{self.risk_class.value}] — reversibility: {self.reversibility}; "
            f"data loss: {self.data_loss}; availability: {self.availability}; "
            f"blast radius: {self.blast_radius}"
        )


#: Every write this feature ships, classified. Ordered by class, least dangerous
#: first, because that is the order a reviewer wants to read them in and the
#: order that makes an out-of-place row visible.
RISK_TABLE: Final[tuple[RiskRow, ...]] = (
    RiskRow(
        capability="proxmox_unlock_guest",
        risk_class=RiskClass.TRIVIAL,
        reversibility="the lock is written back, so the guest returns to exactly its prior state",
        data_loss="none: a lock is a flag in the guest's configuration",
        availability="none: the guest keeps doing whatever it was doing",
        blast_radius="one guest's configuration entry",
    ),
    RiskRow(
        capability="proxmox_start_guest",
        risk_class=RiskClass.LOW,
        reversibility="undone by shutting the guest down again",
        data_loss="none: starting a guest writes nothing of the operator's",
        availability="it adds availability, and can contend for the node's memory and disk",
        blast_radius="one guest, and the node it competes for resources on",
    ),
    RiskRow(
        capability="proxmox_resume_guest",
        risk_class=RiskClass.LOW,
        reversibility="undone by suspending it again",
        data_loss="none: the guest's memory image is restored, not discarded",
        availability="it restores availability the suspend removed",
        blast_radius="one guest",
    ),
    RiskRow(
        capability="proxmox_shutdown_guest",
        risk_class=RiskClass.MODERATE,
        reversibility="undone only by a further action — starting the guest again",
        data_loss="none: the guest's own operating system flushes and closes",
        availability="the guest's own, entirely, until somebody starts it",
        blast_radius="one guest and everything that depends on it",
    ),
    RiskRow(
        capability="proxmox_reboot_guest",
        risk_class=RiskClass.MODERATE,
        reversibility="not an undo: the previous process tree is gone",
        data_loss="none while the shutdown stays graceful",
        availability="the guest's own, for as long as it takes to come back",
        blast_radius="one guest and everything that depends on it",
    ),
    RiskRow(
        capability="proxmox_suspend_guest",
        risk_class=RiskClass.MODERATE,
        reversibility="undone by resuming, which restores the memory image",
        data_loss="none, unless the memory image cannot be written for want of space",
        availability="the guest's own, entirely, until it is resumed",
        blast_radius="one guest, plus the datastore holding its memory image",
    ),
    RiskRow(
        capability="proxmox_migrate_guest",
        risk_class=RiskClass.MODERATE,
        reversibility="undone by migrating back, which is a second move rather than a reversal",
        data_loss="none: an online migration copies memory and leaves the disk where it is",
        availability="a brief pause at the switch-over, and none at all if it fails cleanly",
        blast_radius="the guest, both nodes, and the link between them",
    ),
    RiskRow(
        capability="proxmox_retry_backup",
        risk_class=RiskClass.MODERATE,
        reversibility="not an undo: a backup that ran cannot be un-run",
        data_loss="none: it creates a recovery point rather than removing one",
        availability="I/O contention on the guest and its datastore while it runs",
        blast_radius="one guest, its datastore, and whatever else that datastore serves",
    ),
    RiskRow(
        capability="proxmox_resync_replication",
        risk_class=RiskClass.MODERATE,
        reversibility="not an undo: a sync that ran cannot be un-run",
        data_loss="none on the source; the target is overwritten with the source's state",
        availability="the link between the nodes, which corosync also runs over",
        blast_radius="two nodes and the network between them",
    ),
    RiskRow(
        capability="proxmox_ha_relocate",
        risk_class=RiskClass.HIGH,
        reversibility="undone by writing the previous HA state back, once the manager settles",
        data_loss="none directly",
        availability="the guest stops on one node and starts on another",
        blast_radius="the HA manager's view of the cluster, and every resource it then moves",
    ),
    RiskRow(
        capability="proxmox_stop_guest",
        risk_class=RiskClass.CRITICAL,
        reversibility="starting it again is a recovery, not a reversal",
        data_loss="unflushed writes inside the guest, which is data with no other copy",
        availability="the guest's own, immediately and without warning to anything inside it",
        blast_radius="one guest and everything that depends on it",
        loses_data=True,
    ),
    RiskRow(
        capability="proxmox_reclaim_storage",
        risk_class=RiskClass.CRITICAL,
        reversibility="none: a deleted snapshot or backup has no undo",
        data_loss="whatever the item protected, which may be the only copy of it",
        availability="none directly, and everything if the item was the recovery point",
        blast_radius="every guest whose recovery depended on the items named",
        loses_data=True,
    ),
    RiskRow(
        capability="proxmox_remove_orphaned_volume",
        risk_class=RiskClass.CRITICAL,
        reversibility="none: the volume and its contents are gone",
        data_loss="a whole disk image, which belongs to nobody only as far as anybody checked",
        availability="none, on the evidence that no guest references it",
        blast_radius="one volume on one datastore",
        loses_data=True,
    ),
)

_BY_CAPABILITY: Final[dict[str, RiskRow]] = {row.capability: row for row in RISK_TABLE}


def row_for(capability: str) -> RiskRow:
    """Return ``capability``'s row, or raise naming what the table holds.

    Raises:
        KeyError: the table does not classify that capability.
    """
    found = _BY_CAPABILITY.get(capability)
    if found is None:
        raise KeyError(
            f"{capability!r} is not in the hypervisor risk table, so nobody has classified it. "
            f"The table holds: {', '.join(sorted(_BY_CAPABILITY))}."
        )
    return found


def class_of(capability: str) -> RiskClass:
    """Return the class the table gives ``capability``."""
    return row_for(capability).risk_class


def classified() -> tuple[str, ...]:
    """Return every capability the table classifies, in name order."""
    return tuple(sorted(_BY_CAPABILITY))


@dataclass(frozen=True, slots=True)
class ReclaimableItem:
    """One thing a reclamation could delete, and what it protects.

    ``content`` is the datastore's own word for what the volume is — Proxmox
    reports ``backup``, ``images``, ``iso``, ``snippets`` — and it is what decides
    the class. Size is carried because an operator wants to see it, and is
    deliberately not part of the classification.
    """

    volume_id: str
    content: str
    size_bytes: int = 0
    #: What would be unrecoverable without this item, in the words a proposal
    #: shows. Empty for an item that protects nothing, which is most of them.
    protects: str = ""

    def __post_init__(self) -> None:
        if not self.volume_id.strip():
            raise ValueError("A reclaimable item needs the volume identifier it names.")

    @property
    def is_recovery_point(self) -> bool:
        """Return whether deleting this removes somebody's way back."""
        return self.content.strip().lower() in RECOVERY_POINT_CONTENT


def item_class(item: ReclaimableItem) -> RiskClass:
    """Return how dangerous deleting ``item`` is, by what it protects.

    ``critical`` for a recovery point of any size, and ``high`` for everything
    else — because everything else is still a disk image, and an image nobody
    references is an image nobody has looked for recently.
    """
    return RiskClass.CRITICAL if item.is_recovery_point else RiskClass.HIGH


def reclamation_class(items: tuple[ReclaimableItem, ...]) -> RiskClass:
    """Return the class of deleting ``items`` together, which is the worst of them."""
    if not items:
        return RiskClass.HIGH
    return max((item_class(item) for item in items), key=lambda found: found.rank)


@dataclass(frozen=True, slots=True)
class ProhibitedOperation:
    """Something no capability in this deployment may do, and why it may not."""

    name: str
    why: str
    #: The Proxmox path fragments that would perform it. Matched as substrings of
    #: a request path, because a path is what a write actually reaches and a
    #: capability name is what somebody chooses.
    paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.why.strip() or not self.paths:
            raise ValueError(
                f"{self.name}: a prohibition needs the reason and the paths it covers, or it "
                f"is a rule nothing can enforce."
            )


#: The hole this feature leaves on purpose. In a two-node cluster the system
#: cannot distinguish a dead node from an unreachable one, and both wrong answers
#: are expensive: fencing a live node kills its running guests, and starting them
#: elsewhere while it still runs them corrupts shared state. No autonomy level
#: should be able to resolve that ambiguity, so no capability offers it.
PROHIBITED_OPERATIONS: Final[tuple[ProhibitedOperation, ...]] = (
    ProhibitedOperation(
        name="fencing",
        why=(
            "fencing a node that is merely unreachable kills guests that are still serving, "
            "and no reading available to this system tells the two cases apart"
        ),
        paths=("/nodes/{node}/status?command=reset", "/cluster/ha/fence", "/watchdog"),
    ),
    ProhibitedOperation(
        name="quorum",
        why=(
            "forcing quorum lets a partitioned cluster decide twice, which is how one guest "
            "ends up running on both nodes and writing to the same disk"
        ),
        paths=("/cluster/config/qdevice", "expected=", "/cluster/config/join"),
    ),
    ProhibitedOperation(
        name="corosync",
        why=(
            "the membership layer is what every other reading depends on; a write here that "
            "is wrong takes the cluster filesystem read-only and the recovery is physical"
        ),
        paths=("/cluster/config/totem", "/cluster/config/nodes", "corosync"),
    ),
    ProhibitedOperation(
        name="node_services",
        why=(
            "pveproxy, pvedaemon, pve-cluster and corosync are how this system reaches the "
            "cluster at all; restarting one is a proposal to a human, never an action"
        ),
        paths=("/nodes/{node}/services", "/nodes/{node}/stopall", "/nodes/{node}/status?command="),
    ),
    ProhibitedOperation(
        name="node_network",
        why=(
            "a node's interfaces, bridges, bonds and routes are owned by a declarative "
            "control plane with its own apply path, and a second writer turns drift into "
            "an outage that needs physical access to recover"
        ),
        paths=("/nodes/{node}/network", "/nodes/{node}/hosts", "/nodes/{node}/dns"),
    ),
    ProhibitedOperation(
        name="pool_extension",
        why=(
            "extending a thin pool or a ZFS pool consumes the only spare capacity a node "
            "has, and choosing to spend it is a decision with a budget attached"
        ),
        paths=("/nodes/{node}/disks/lvmthin", "/nodes/{node}/disks/zfs", "/nodes/{node}/disks/lvm"),
    ),
)

#: The literal ``{node}`` in a declared path is a placeholder, so matching strips
#: it and compares the halves. Written once because every prohibition uses it.
_NODE_PLACEHOLDER: Final = "{node}"


def prohibition_for(path: str) -> ProhibitedOperation | None:
    """Return the prohibition ``path`` would breach, or ``None`` when it breaches none."""
    for prohibition in PROHIBITED_OPERATIONS:
        for fragment in prohibition.paths:
            if _matches(path, fragment):
                return prohibition
    return None


def _matches(path: str, fragment: str) -> bool:
    """Return whether ``path`` contains ``fragment``, treating ``{node}`` as any name."""
    if _NODE_PLACEHOLDER not in fragment:
        return fragment in path
    head, tail = fragment.split(_NODE_PLACEHOLDER, 1)
    if head not in path:
        return False
    remainder = path.split(head, 1)[1]
    # One path segment stands in for the node name; anything beyond that would
    # make ``/nodes/{node}/network`` match ``/nodes/a/b/c/network``, which is a
    # different endpoint and would refuse a write nobody prohibited.
    segment, _, rest = remainder.partition("/")
    return bool(segment) and (f"/{rest}").startswith(tail)


def describe_table() -> str:
    """Return the whole table as the block a review or a report prints."""
    return "\n".join(row.describe() for row in RISK_TABLE)


__all__ = [
    "PROHIBITED_OPERATIONS",
    "RECOVERY_POINT_CONTENT",
    "RISK_TABLE",
    "ProhibitedOperation",
    "ReclaimableItem",
    "RiskRow",
    "class_of",
    "classified",
    "describe_table",
    "item_class",
    "prohibition_for",
    "reclamation_class",
    "row_for",
]
