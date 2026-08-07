"""The measured shape of the deployment this dataset describes.

Every number here came off a real two-node cluster: the count of guests and the
ratio between containers and virtual machines, the skew that puts almost
everything that runs on one node, the three volumes near their own ceiling while
their datastore reads comfortable, the backup job that exists and is switched
off, the nine failed units on one host, the two datastores answering unknown.
Those are the properties nobody invents, and they are the ones the console has
to survive.

Every *name* here is a pseudonym. The survey the numbers came from is not in
this repository and the values that would identify it never were; what is
recorded is shape, scale, distribution and the awkwardness.

The guests are generated rather than listed, from the declared counts and the
declared skew, because eighty-four hand-written entries would be eighty-four
chances for the ratio to drift from what was measured. The ones that carry an
awkward property are declared explicitly — those are the point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from tools.mockplane.capture.parsers import (
    PackageReading,
    QuorumReading,
    ThinPoolReading,
    VolumeReading,
)
from tools.mockplane.capture.projection import (
    BackupJobReading,
    ClusterReading,
    DatastoreReading,
    GuestReading,
    NodeReading,
)

#: When the survey was taken, before the pipeline shifts everything onto the
#: fixed reference instant. Kept as a real interval from that instant so the
#: history reads as a history rather than as one moment.
CAPTURED_AT: Final = "2026-08-07T09:41:00+00:00"

PRIMARY_NODE: Final = "node01"
SECONDARY_NODE: Final = "node02"

#: Eighty-four guests, of which two are virtual machines. The ratio is the
#: finding: a console designed against an even mix of both would be a console
#: designed against something that does not exist here.
TOTAL_GUESTS: Final = 84
VIRTUAL_MACHINES: Final = 2
GUESTS_ON_PRIMARY: Final = 55

#: Load is markedly asymmetric. The primary carries almost everything that runs;
#: the secondary carries a warm pool and the heavy stateful guests.
RUNNING_ON_PRIMARY: Final = 52
RUNNING_ON_SECONDARY: Final = 18

_GUEST_WORDS: Final[tuple[str, ...]] = (
    "alder",
    "amber",
    "anchor",
    "arbour",
    "aspen",
    "basalt",
    "beacon",
    "beryl",
    "birch",
    "bramble",
    "brook",
    "cairn",
    "cedar",
    "cinder",
    "cobalt",
    "copper",
    "coral",
    "cove",
    "crag",
    "cypress",
    "delta",
    "dune",
    "ember",
    "fathom",
    "fennel",
    "fjord",
    "flint",
    "gable",
    "garnet",
    "granite",
    "harbour",
    "hazel",
    "heather",
    "hollow",
    "indigo",
    "ivory",
    "jasper",
    "juniper",
    "kelp",
    "lagoon",
    "larch",
    "laurel",
    "ledger",
    "linen",
    "lumen",
    "maple",
    "marble",
    "meadow",
    "mesa",
    "mica",
    "mint",
    "moss",
    "nickel",
    "nimbus",
    "oakum",
    "obsidian",
    "onyx",
    "opal",
    "orchard",
    "osprey",
    "pebble",
    "pewter",
    "pine",
    "plateau",
    "poplar",
    "quarry",
    "quartz",
    "quill",
    "ridge",
    "rowan",
    "rushes",
    "sable",
    "saffron",
    "sandstone",
    "sequoia",
    "shale",
    "shingle",
    "silver",
    "slate",
    "sorrel",
    "spruce",
    "stone",
    "sumac",
    "tamarisk",
)


@dataclass(frozen=True, slots=True)
class NotableGuest:
    """A guest that carries something worth keeping."""

    vmid: str
    name: str
    node: str
    volume_percent: float
    note: str


#: The guests at or near the ceiling of their own volumes. The first is at
#: 99.6% while the datastore under it reads 84% — precisely the distinction a
#: datastore-level threshold cannot make, and the reason both numbers are in
#: this dataset.
NOTABLE_GUESTS: Final[tuple[NotableGuest, ...]] = (
    NotableGuest("100", "plateau", SECONDARY_NODE, 99.60, "at the ceiling of its own volume"),
    NotableGuest("115", "quartz", SECONDARY_NODE, 94.96, "name resolution stalled twice"),
    NotableGuest("140", "sorrel", SECONDARY_NODE, 93.00, "name resolution stalled twice"),
    NotableGuest("161", "lumen", SECONDARY_NODE, 76.88, "comfortable, for contrast"),
    NotableGuest("142", "harbour", SECONDARY_NODE, 74.21, "comfortable, for contrast"),
)

#: Nine failed units on the primary, one on the secondary. Two of the primary's
#: are network shares that are down — which is why two datastores answer
#: unknown — and one is the hardening script a postmortem singled out for
#: failing silently. It now fails loudly and nothing is watching.
PRIMARY_FAILED_UNITS: Final[tuple[str, ...]] = (
    "corosync-qdevice.service",
    "gateway-hardening.service",
    "metrics-agent.service",
    "mnt-archive.mount",
    "mnt-media.mount",
    "mnt-vault.mount",
    "netbios.service",
    "platform-management.service",
    "vault-route.service",
)
SECONDARY_FAILED_UNITS: Final[tuple[str, ...]] = ("platform-management.service",)

#: Twenty-four packages pending on both nodes, six of them security. Including
#: a kernel that is installed and has never been booted, which is the exact
#: precondition of the outage this cluster has already had.
PENDING_PACKAGES: Final = 24
SECURITY_PACKAGES: Final = 6
KERNEL_RUNNING: Final = "7.0.14-8"
KERNEL_INSTALLED: Final = "7.0.14-9"

#: Two thin pools, and the one that matters reads 72% of its data while its
#: metadata is at 32%. Metadata exhaustion takes a pool offline while the number
#: everybody watches still looks fine.
THIN_POOLS: Final[tuple[tuple[str, str, int, float, float], ...]] = (
    ("pool-system", "pool-system", 375_722_000_000, 84.46, 3.35),
    ("pool-bulk", "pool-bulk", 999_750_000_000, 72.38, 31.98),
)

#: Eleven datastores. Two answer ``unknown`` — network shares that are down —
#: and the two fullest are past any threshold worth having.
DATASTORES: Final[tuple[tuple[str, str, str, int | None, int | None, str], ...]] = (
    ("store-cove", PRIMARY_NODE, "cifs", 7_654_000_000_000, 8_002_000_000_000, "available"),
    ("store-ridge", PRIMARY_NODE, "cifs", 1_869_000_000_000, 2_000_000_000_000, "available"),
    ("local-lvm", SECONDARY_NODE, "lvmthin", 315_000_000_000, 375_000_000_000, "available"),
    ("local", SECONDARY_NODE, "dir", 82_600_000_000, 103_000_000_000, "available"),
    ("store-fjord", PRIMARY_NODE, "cifs", 3_200_000_000_000, 4_000_000_000_000, "available"),
    ("store-meadow", PRIMARY_NODE, "nfs", 1_540_000_000_000, 2_000_000_000_000, "available"),
    ("store-linen", SECONDARY_NODE, "dir", 750_000_000_000, 1_000_000_000_000, "available"),
    ("local-lvm", PRIMARY_NODE, "lvmthin", 210_000_000_000, 375_000_000_000, "available"),
    ("store-tundra", PRIMARY_NODE, "cifs", 380_000_000_000, 2_000_000_000_000, "available"),
    ("store-osprey", PRIMARY_NODE, "nfs", None, None, "unknown"),
    ("store-kelp", PRIMARY_NODE, "nfs", None, None, "unknown"),
)

#: Three backup jobs. The one covering the primary's fifty-five guests exists
#: and is disabled; the one covering the secondary names ten of twenty-nine; the
#: third is disabled too. Retention is two throughout, so the second failed
#: backup destroys what the first one left.
BACKUP_JOBS: Final[tuple[tuple[str, str, str | None, str, bool, bool, tuple[str, ...]], ...]] = (
    ("backup-7d831311", "primary baseline", None, "08:00", False, True, ()),
    (
        "backup-33b5e58a",
        "secondary baseline",
        SECONDARY_NODE,
        "07:00",
        True,
        False,
        ("100", "102", "104", "106", "108", "110", "112", "114", "116", "118"),
    ),
    ("backup-1f376301", "relational store", SECONDARY_NODE, "02:30,22:30", False, False, ("129",)),
)

BACKUP_KEEP_LAST: Final = 2


def _guest_state(index: int, running_on_node: int) -> str:
    """Return whether the ``index``-th guest on a node is running.

    Deterministic and skewed to match what was measured: the primary runs almost
    everything it holds, the secondary keeps a warm pool that is stopped.
    """
    return "running" if index < running_on_node else "stopped"


def guests() -> tuple[GuestReading, ...]:
    """Return the estate's guests, at the measured counts, ratio and skew."""
    notable = {entry.vmid: entry for entry in NOTABLE_GUESTS}
    found: list[GuestReading] = []
    primary_index = 0
    secondary_index = 0

    for ordinal in range(TOTAL_GUESTS):
        vmid = str(100 + ordinal)
        on_primary = ordinal >= TOTAL_GUESTS - GUESTS_ON_PRIMARY
        node = PRIMARY_NODE if on_primary else SECONDARY_NODE
        if on_primary:
            state = _guest_state(primary_index, RUNNING_ON_PRIMARY)
            primary_index += 1
        else:
            state = _guest_state(secondary_index, RUNNING_ON_SECONDARY)
            secondary_index += 1

        declared = notable.get(vmid)
        name = declared.name if declared else _GUEST_WORDS[ordinal % len(_GUEST_WORDS)]
        if declared is not None:
            node = declared.node
        # The two virtual machines are the last two ids, which is where they sit
        # in the survey: everything else is a container.
        kind = "virtual-machine" if ordinal >= TOTAL_GUESTS - VIRTUAL_MACHINES else "container"
        found.append(
            GuestReading(
                vmid=vmid,
                name=name,
                kind=kind,
                node=node,
                state=state,
                cpu_percent=round((ordinal % 17) * 1.7, 2) if state == "running" else 0.0,
                memory_percent=round(18.0 + (ordinal % 23) * 2.9, 2) if state == "running" else 0.0,
                tags=("stateful",) if declared is not None else (),
            )
        )
    return tuple(found)


def volumes_on(node: str) -> tuple[VolumeReading, ...]:
    """Return the thin volumes on ``node``, the near-full ones among them."""
    if node != SECONDARY_NODE:
        return ()
    return tuple(
        VolumeReading(
            name=f"vm-{entry.vmid}-disk-0",
            volume_group="pool-bulk",
            pool="pool-bulk",
            size_bytes=64_000_000_000,
            used_percent=entry.volume_percent,
        )
        for entry in NOTABLE_GUESTS
    )


def packages() -> tuple[PackageReading, ...]:
    """Return the pending packages, the security subset among them."""
    found: list[PackageReading] = []
    for ordinal in range(PENDING_PACKAGES):
        is_security = ordinal < SECURITY_PACKAGES
        name = "kernel-platform" if ordinal == SECURITY_PACKAGES else f"package-{ordinal:02d}"
        found.append(
            PackageReading(
                name=name,
                version=KERNEL_INSTALLED if name == "kernel-platform" else f"1.{ordinal}.0",
                is_security=is_security,
            )
        )
    return tuple(found)


def nodes() -> tuple[NodeReading, ...]:
    """Return both nodes, with the load skew and the failed units intact."""
    pools = tuple(
        ThinPoolReading(
            name=name,
            volume_group=group,
            size_bytes=size,
            data_percent=data,
            metadata_percent=metadata,
        )
        for name, group, size, data, metadata in THIN_POOLS
    )
    return (
        NodeReading(
            name=PRIMARY_NODE,
            role="primary",
            version="9.2.6",
            kernel_running=KERNEL_RUNNING,
            kernel_installed=KERNEL_INSTALLED,
            cpu_percent=63.0,
            memory_percent=58.0,
            root_filesystem_percent=33.0,
            failed_units=PRIMARY_FAILED_UNITS,
            thin_pools=(),
            volumes=(),
            packages=packages(),
            bridges=("bridge0",),
            zfs_pools=(),
        ),
        NodeReading(
            name=SECONDARY_NODE,
            role="secondary",
            version="9.2.6",
            kernel_running=KERNEL_RUNNING,
            kernel_installed=KERNEL_INSTALLED,
            cpu_percent=9.0,
            memory_percent=51.0,
            root_filesystem_percent=80.0,
            failed_units=SECONDARY_FAILED_UNITS,
            thin_pools=pools,
            volumes=volumes_on(SECONDARY_NODE),
            packages=packages(),
            bridges=("bridge0",),
            zfs_pools=(),
        ),
    )


def datastores() -> tuple[DatastoreReading, ...]:
    """Return every datastore, the two answering ``unknown`` among them."""
    return tuple(
        DatastoreReading(
            name=name, node=node, kind=kind, used_bytes=used, total_bytes=total, status=status
        )
        for name, node, kind, used, total, status in DATASTORES
    )


def backup_jobs() -> tuple[BackupJobReading, ...]:
    """Return the backup jobs, including the one that exists and is disabled."""
    return tuple(
        BackupJobReading(
            job_id=job_id,
            comment=comment,
            node=node,
            schedule=schedule,
            enabled=enabled,
            covers_all=covers_all,
            vmids=vmids,
            keep_last=BACKUP_KEEP_LAST,
        )
        for job_id, comment, node, schedule, enabled, covers_all, vmids in BACKUP_JOBS
    )


def quorum() -> QuorumReading:
    """Return quorum as measured: two of two required, and no margin at all.

    A quorum device appears in the membership view, contributes zero votes, and
    the configuration declares none. Losing either node makes the cluster
    filesystem read-only.
    """
    return QuorumReading(
        expected_votes=2,
        total_votes=2,
        quorum=2,
        quorate=True,
        config_version=2,
        two_node=False,
        wait_for_all=False,
        device_declared=False,
        device_in_membership=True,
        node_names=(PRIMARY_NODE, SECONDARY_NODE),
    )


def cluster_reading() -> ClusterReading:
    """Return the whole survey as one value the projection turns into fixtures."""
    return ClusterReading(
        captured_at=CAPTURED_AT,
        nodes=nodes(),
        guests=guests(),
        datastores=datastores(),
        backup_jobs=backup_jobs(),
        quorum=quorum(),
        replication_jobs=(),
    )


def guest_names() -> Sequence[str]:
    """Return the guests' names, for the parts of the dataset that mention one."""
    return [guest.name for guest in guests()]


__all__ = [
    "BACKUP_JOBS",
    "BACKUP_KEEP_LAST",
    "CAPTURED_AT",
    "DATASTORES",
    "GUESTS_ON_PRIMARY",
    "KERNEL_INSTALLED",
    "KERNEL_RUNNING",
    "NOTABLE_GUESTS",
    "PENDING_PACKAGES",
    "PRIMARY_FAILED_UNITS",
    "PRIMARY_NODE",
    "RUNNING_ON_PRIMARY",
    "RUNNING_ON_SECONDARY",
    "SECONDARY_FAILED_UNITS",
    "SECONDARY_NODE",
    "SECURITY_PACKAGES",
    "THIN_POOLS",
    "TOTAL_GUESTS",
    "VIRTUAL_MACHINES",
    "NotableGuest",
    "backup_jobs",
    "cluster_reading",
    "datastores",
    "guest_names",
    "guests",
    "nodes",
    "packages",
    "quorum",
    "volumes_on",
]
