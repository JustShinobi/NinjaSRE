"""A two-node Proxmox cluster, recorded, in five states — and no live cluster.

Every Proxmox test in this repository reads from here. That is the whole of
NFR-004: the client is exercised end to end against responses that were captured
from a real cluster rather than invented, and nothing in the suite needs an
address, a token, or a hypervisor that is up.

The five states are the ones that change what a reader has to conclude:

``HEALTHY``
    Both nodes up, quorate, everything answering. The baseline the others are
    read against.
``DEGRADED``
    Quorate, but the things a datastore-level threshold cannot see are true: a
    thin pool near its metadata ceiling, a guest at 99% of its own volume, two
    datastores reporting ``unknown`` because their NFS mounts are down.
``NO_QUORUM``
    The cluster answers ``quorate: 0``. Several reads still work; the ones that
    need ``/etc/pve`` writable do not. A client that treated this as a
    connection failure would hide the single most important fact about a
    two-node cluster.
``NODE_DOWN``
    One node is offline. The cluster and the survivor still enumerate, and the
    down node's guests are still *listed* by the cluster resource endpoint with
    a status the estate reads as stale rather than absent.
``SINGLE_NODE``
    An installation with no cluster at all, which answers the cluster endpoints
    with a single standalone node and no corosync configuration.

The numbers are the reference cluster's own: 349.9G and 931.1G thin pools, a
plex volume at 99.6%, `TeraChad` at 96%, a disabled backup job covering the node
that carries almost everything, and no replication jobs whatsoever. Invented
numbers would let a threshold be wrong in exactly the direction that never fires.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

from integrations._base.access import IntegrationAccess, bind, restore
from integrations._base.client import IntegrationClient
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.retry import RetryPolicy
from integrations._base.transport import RequestContext
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.schema import API_BASE, INTEGRATION
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

PRIMARY: Final = "pve01"
SECONDARY: Final = "pve02"
CLUSTER: Final = "HAL9000"
VERSION: Final = "9.2.6"


class ClusterState(StrEnum):
    """Which recorded state a fixture set describes."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    NO_QUORUM = "no_quorum"
    NODE_DOWN = "node_down"
    SINGLE_NODE = "single_node"


def data(payload: Any) -> dict[str, Any]:
    """Return ``payload`` wrapped the way every Proxmox endpoint answers."""
    return {"data": payload}


# --- /cluster/status ----------------------------------------------------------


def _cluster_status(state: ClusterState) -> list[dict[str, Any]]:
    """Return the membership view for ``state``."""
    if state is ClusterState.SINGLE_NODE:
        return [
            {
                "type": "node",
                "id": f"node/{PRIMARY}",
                "name": PRIMARY,
                "online": 1,
                "local": 1,
                "ip": "192.168.68.149",
            }
        ]

    quorate = 0 if state is ClusterState.NO_QUORUM else 1
    votes = 1 if state in {ClusterState.NO_QUORUM, ClusterState.NODE_DOWN} else 2
    secondary_online = 0 if state is ClusterState.NODE_DOWN else 1
    return [
        {
            "type": "cluster",
            "id": "cluster",
            "name": CLUSTER,
            "version": 2,
            "nodes": 2,
            "quorate": quorate,
        },
        {
            "type": "node",
            "id": f"node/{PRIMARY}",
            "name": PRIMARY,
            "online": 1,
            "local": 0,
            "ip": "192.168.68.149",
            "nodeid": 1,
        },
        {
            "type": "node",
            "id": f"node/{SECONDARY}",
            "name": SECONDARY,
            "online": secondary_online,
            "local": 1,
            "ip": "192.168.68.159",
            "nodeid": 2,
        },
    ] + [
        {
            "type": "quorum",
            "id": "quorum",
            "quorate": quorate,
            "expected_votes": 2,
            "total_votes": votes,
            "quorum": 2,
            "qdevice": "NA,NV,NMW",
        }
    ]


# --- /cluster/resources -------------------------------------------------------

#: The guests the reference cluster runs, trimmed to the ones the tests read.
#: ``vmid`` 100, 115 and 140 are the three whose own volumes are near full;
#: 9000 is the virtual machine, and it is here because a catalogue that only
#: ever saw containers would let "guest" and "container" be the same word.
_GUESTS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "lxc/100",
        "type": "lxc",
        "vmid": 100,
        "name": "plex",
        "node": SECONDARY,
        "status": "running",
        "maxcpu": 4,
        "maxmem": 4294967296,
        "maxdisk": 107374182400,
        "uptime": 813_244,
        "template": 0,
    },
    {
        "id": "lxc/115",
        "type": "lxc",
        "vmid": 115,
        "name": "adguard",
        "node": SECONDARY,
        "status": "running",
        "maxcpu": 1,
        "maxmem": 536870912,
        "maxdisk": 8589934592,
        "uptime": 813_190,
        "template": 0,
    },
    {
        "id": "lxc/140",
        "type": "lxc",
        "vmid": 140,
        "name": "unbound",
        "node": SECONDARY,
        "status": "running",
        "maxcpu": 1,
        "maxmem": 268435456,
        "maxdisk": 4294967296,
        "uptime": 812_998,
        "template": 0,
    },
    {
        "id": "lxc/137",
        "type": "lxc",
        # A guest with no name set: Proxmox omits the key entirely rather than
        # sending an empty string, which is the shape a reader has to survive.
        "vmid": 137,
        "node": PRIMARY,
        "status": "running",
        "maxcpu": 2,
        "maxmem": 2147483648,
        "maxdisk": 34359738368,
        "uptime": 604_800,
        "template": 0,
    },
    {
        "id": "qemu/9000",
        "type": "qemu",
        "vmid": 9000,
        "name": "windows-lab",
        "node": PRIMARY,
        "status": "stopped",
        "maxcpu": 4,
        "maxmem": 8589934592,
        "maxdisk": 137438953472,
        "uptime": 0,
        "template": 0,
    },
)

#: Every datastore the cluster reports, with the fill the survey measured.
_STORAGE: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": f"storage/{SECONDARY}/TeraChad",
        "type": "storage",
        "storage": "TeraChad",
        "node": SECONDARY,
        "status": "available",
        "plugintype": "cifs",
        "shared": 1,
        "maxdisk": 8_001_000_000_000,
        "disk": 7_654_000_000_000,
    },
    {
        "id": f"storage/{SECONDARY}/GigaChad",
        "type": "storage",
        "storage": "GigaChad",
        "node": SECONDARY,
        "status": "available",
        "plugintype": "cifs",
        "shared": 1,
        "maxdisk": 2_000_000_000_000,
        "disk": 1_869_000_000_000,
    },
    {
        "id": f"storage/{SECONDARY}/local-lvm",
        "type": "storage",
        "storage": "local-lvm",
        "node": SECONDARY,
        "status": "available",
        "plugintype": "lvmthin",
        "shared": 0,
        "maxdisk": 375_700_000_000,
        "disk": 317_300_000_000,
    },
    {
        "id": f"storage/{PRIMARY}/local-lvm",
        "type": "storage",
        "storage": "local-lvm",
        "node": PRIMARY,
        "status": "available",
        "plugintype": "lvmthin",
        "shared": 0,
        "maxdisk": 375_700_000_000,
        "disk": 210_400_000_000,
    },
    {
        "id": f"storage/{PRIMARY}/externo-nfs-pve01",
        "type": "storage",
        "storage": "externo-nfs-pve01",
        "node": PRIMARY,
        # An NFS mount that is down. Proxmox reports the datastore as unknown
        # rather than absent, and "unknown" is not "available".
        "status": "unknown",
        "plugintype": "nfs",
        "shared": 1,
    },
)


def _cluster_resources(state: ClusterState) -> list[dict[str, Any]]:
    """Return the cluster-wide resource list for ``state``."""
    if state is ClusterState.SINGLE_NODE:
        nodes = [
            {
                "id": f"node/{PRIMARY}",
                "type": "node",
                "node": PRIMARY,
                "status": "online",
                "maxcpu": 8,
                "maxmem": 33_284_000_000,
                "uptime": 813_600,
            }
        ]
        return nodes + [dict(guest) for guest in _GUESTS if guest["node"] == PRIMARY]

    secondary_status = "offline" if state is ClusterState.NODE_DOWN else "online"
    nodes = [
        {
            "id": f"node/{PRIMARY}",
            "type": "node",
            "node": PRIMARY,
            "status": "online",
            "maxcpu": 8,
            "maxmem": 33_284_000_000,
            "uptime": 813_600,
        },
        {
            "id": f"node/{SECONDARY}",
            "type": "node",
            "node": SECONDARY,
            "status": secondary_status,
            "maxcpu": 12,
            "maxmem": 67_355_000_000,
            "uptime": 0 if state is ClusterState.NODE_DOWN else 813_600,
        },
    ]

    guests = []
    for guest in _GUESTS:
        record = dict(guest)
        if state is ClusterState.NODE_DOWN and record["node"] == SECONDARY:
            # A guest on a node that is not answering. Proxmox keeps the row and
            # blanks what it cannot currently see, which is the difference
            # between a stale reading and a deleted guest.
            record["status"] = "unknown"
            record["uptime"] = 0
        guests.append(record)

    return nodes + guests + [dict(store) for store in _STORAGE]


# --- The rest of the endpoints ------------------------------------------------

_VERSION: Final = {"version": VERSION, "release": "9.2", "repoid": "0f1a2b3c"}

_HA_RESOURCES: Final = [
    {"sid": "ct:115", "type": "ct", "state": "started", "group": "dns", "max_restart": 1},
]

_HA_STATUS: Final = [
    {"id": "master", "type": "master", "node": PRIMARY, "status": "master", "quorate": 1},
    {
        "id": f"lrm:{SECONDARY}",
        "type": "lrm",
        "node": SECONDARY,
        "status": "wait_for_agent_lock",
        "mode": "active",
    },
    {
        # One managed service, with the pair of states that matter: what the
        # manager wants and what the resource is actually doing. They agree here;
        # a resource whose requested state is ``started`` and whose current state
        # is ``fence`` is a node about to be reset.
        "id": "service:ct:115",
        "type": "service",
        "sid": "ct:115",
        "node": SECONDARY,
        "state": "started",
        "request_state": "started",
        "crm_state": "started",
    },
]

_BACKUP_JOBS: Final = [
    {
        "id": "backup-7d831311",
        "comment": "pve01 baseline",
        "enabled": 0,
        "all": 1,
        "schedule": "08:00",
        "storage": "remote-backup",
        "node": PRIMARY,
        "mode": "snapshot",
        # Thirty retained copies on the job that is switched off, and two on the
        # one that runs. Coverage without depth reads these as the same job.
        "prune-backups": "keep-daily=30",
    },
    {
        "id": "backup-33b5e58a",
        "comment": "pve02 baseline",
        "enabled": 1,
        "vmid": "100,115,140,142,161",
        "schedule": "07:00",
        "storage": "remote-backup",
        "node": SECONDARY,
        "mode": "snapshot",
        "prune-backups": "keep-last=2",
    },
]

_LVM_THIN: Final = [
    {
        "lv": "data",
        "vg": "pve",
        "lv_size": 375_700_000_000,
        "data_percent": 84.46,
        "metadata_percent": 3.35,
        "lv_state": "available",
    },
    {
        "lv": "data-pool",
        "vg": "data-pool",
        "lv_size": 999_800_000_000,
        "data_percent": 72.38,
        # A thin pool that exhausts its metadata stops accepting writes while
        # its data percentage still looks fine. The two are separate readings
        # and a client that reported one would report this pool as healthy.
        "metadata_percent": 31.98,
        "lv_state": "available",
    },
]

_LVM_VOLUMES: Final = [
    {"lv": "vm-100-disk-0", "vg": "data-pool", "lv_size": 107_374_182_400, "data_percent": 99.60},
    {"lv": "vm-115-disk-0", "vg": "pve", "lv_size": 8_589_934_592, "data_percent": 94.96},
    {"lv": "vm-140-disk-0", "vg": "pve", "lv_size": 4_294_967_296, "data_percent": 93.00},
    {"lv": "vm-9000-disk-0", "vg": "pve", "lv_size": 137_438_953_472, "data_percent": 41.20},
]

#: The cluster-wide datastore definitions, which is a different reading from what
#: any one node currently sees. ``nodes`` restricts a datastore to a subset, and
#: an empty value means every node — the field that decides whether a guest can
#: move at all, because a guest cannot follow its disk to a node that has none.
_STORAGE_CONFIGURATION: Final[tuple[dict[str, Any], ...]] = (
    {"storage": "local-lvm", "type": "lvmthin", "content": "images,rootdir", "nodes": ""},
    {
        "storage": "data-pool",
        "type": "lvmthin",
        "content": "images,rootdir",
        "nodes": SECONDARY,
    },
    {
        "storage": "TeraChad",
        "type": "cifs",
        "content": "backup,iso",
        "shared": 1,
        "nodes": SECONDARY,
    },
    {
        "storage": "GigaChad",
        "type": "cifs",
        "content": "images,backup",
        "shared": 1,
        "nodes": SECONDARY,
    },
    {
        "storage": "externo-nfs-pve01",
        "type": "nfs",
        "content": "backup",
        "shared": 1,
        "nodes": PRIMARY,
    },
)

#: One node's SMART report, keyed by device. Proxmox answers ``/disks/smart`` with
#: a health verdict and the vendor's own attribute table, and the attributes are
#: the half that predicts: a drive that still says ``PASSED`` while its pending
#: sector count climbs is the ordinary way a disk fails.
_SMART: Final[dict[str, dict[str, Any]]] = {
    "/dev/nvme0n1": {
        "health": "PASSED",
        "type": "text",
        "attributes": [
            {"id": 5, "name": "Reallocated_Sector_Ct", "raw": "0", "value": 100, "threshold": 10},
            {"id": 9, "name": "Power_On_Hours", "raw": "14203", "value": 99, "threshold": 0},
            {
                "id": 233,
                "name": "Media_Wearout_Indicator",
                "raw": "97",
                "value": 97,
                "threshold": 5,
            },
        ],
    },
    "/dev/sda": {
        "health": "PASSED",
        "type": "ata",
        "attributes": [
            {"id": 5, "name": "Reallocated_Sector_Ct", "raw": "184", "value": 96, "threshold": 10},
            {"id": 9, "name": "Power_On_Hours", "raw": "51204", "value": 63, "threshold": 0},
            {
                "id": 197,
                "name": "Current_Pending_Sector",
                "raw": "24",
                "value": 100,
                "threshold": 0,
            },
        ],
    },
}

#: The cluster log, which is where corosync's own account of its links lives.
#: Two links behaving differently on purpose: ring 0 goes down and back up four
#: times inside two minutes, and ring 1 goes down once and never returns. Those
#: are the same "is down" line and completely different faults — a flapping link
#: is a cable or a switch port, a lost one is an address that no longer exists.
_CLUSTER_LOG: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": 1,
        "node": PRIMARY,
        "pri": 3,
        "tag": "corosync",
        "time": 1_754_802_000,
        "msg": "link: host: 2 link: 1 is down",
    },
    {
        "id": 2,
        "node": PRIMARY,
        "pri": 3,
        "tag": "corosync",
        "time": 1_754_802_030,
        "msg": "link: host: 2 link: 0 is down",
    },
    {
        "id": 3,
        "node": PRIMARY,
        "pri": 5,
        "tag": "corosync",
        "time": 1_754_802_035,
        "msg": "link: host: 2 link: 0 is up",
    },
    {
        "id": 4,
        "node": PRIMARY,
        "pri": 4,
        "tag": "corosync",
        "time": 1_754_802_040,
        "msg": "Retransmit List: 1a 1b 1c",
    },
    {
        "id": 5,
        "node": PRIMARY,
        "pri": 3,
        "tag": "corosync",
        "time": 1_754_802_060,
        "msg": "link: host: 2 link: 0 is down",
    },
    {
        "id": 6,
        "node": PRIMARY,
        "pri": 5,
        "tag": "corosync",
        "time": 1_754_802_075,
        "msg": "link: host: 2 link: 0 is up",
    },
    {
        "id": 7,
        "node": SECONDARY,
        "pri": 4,
        "tag": "corosync",
        "time": 1_754_802_090,
        "msg": "Retransmit List: 21 22",
    },
)

#: A ZFS pool, for the deployments that have one. Neither reference node does,
#: which is why the healthy corpus answers ``/disks/zfs`` with an empty list and
#: a test that needs a pool supplies it. This is what such a node would say.
ZFS_POOLS: Final[tuple[dict[str, Any], ...]] = (
    {
        "name": "tank",
        "size": 4_000_787_030_016,
        "alloc": 3_840_755_546_895,
        "free": 160_031_483_121,
        "frag": 47,
        "health": "ONLINE",
        "dedup": 1.0,
    },
)

#: One pool's detail, as ``/disks/zfs/<pool>`` answers it: the device tree with
#: per-device error counters, the scrub line, and the pool's own error summary.
ZFS_POOL_DETAIL: Final[dict[str, Any]] = {
    "name": "tank",
    "state": "ONLINE",
    "errors": "No known data errors",
    "scan": "scrub repaired 0B in 04:12:31 with 0 errors on Sun Jun  8 04:12:31 2025",
    "children": [
        {
            "name": "mirror-0",
            "state": "ONLINE",
            "read": 0,
            "write": 0,
            "cksum": 0,
            "leaf": 0,
            "children": [
                {"name": "sda", "state": "ONLINE", "read": 0, "write": 0, "cksum": 0, "leaf": 1},
                # A device accumulating checksum errors inside a pool that still
                # says ONLINE. The pool's own word is the last thing to change.
                {"name": "sdd", "state": "ONLINE", "read": 0, "write": 0, "cksum": 2, "leaf": 1},
            ],
        }
    ],
}


@dataclass(frozen=True, slots=True)
class RecordedCluster:
    """Every recorded response for one cluster state, keyed by API path.

    Keyed by path rather than ordered as a queue, because a client whose call
    order changes should not need every fixture rewritten — and because a test
    that asserts *which* paths were reached is more useful than one that asserts
    how many.
    """

    state: ClusterState
    responses: Mapping[str, Any] = field(default_factory=dict)

    def payload(self, path: str) -> Any:
        """Return the recorded body for ``path``.

        Raises:
            KeyError: no response was recorded for that path, which is a fixture
                gap rather than a cluster that answered nothing.
        """
        if path not in self.responses:
            raise KeyError(
                f"no recorded Proxmox response for {path!r} in the {self.state.value} state"
            )
        return self.responses[path]

    def paths(self) -> tuple[str, ...]:
        """Return every path this state has a recording for, in name order."""
        return tuple(sorted(self.responses))


def recorded(state: ClusterState) -> RecordedCluster:
    """Return the recorded corpus for ``state``."""
    single = state is ClusterState.SINGLE_NODE
    down = state is ClusterState.NODE_DOWN
    degraded = state in {ClusterState.DEGRADED, ClusterState.NO_QUORUM}

    responses: dict[str, Any] = {
        "/version": _VERSION,
        "/cluster/status": _cluster_status(state),
        "/cluster/resources": _cluster_resources(state),
        "/cluster/config/nodes": (
            []
            if single
            else [
                {
                    "node": PRIMARY,
                    "nodeid": 1,
                    "ring0_addr": "192.168.68.149",
                    # A second corosync ring on one node and not on the other.
                    # Corosync builds links pairwise, so a ring only one node
                    # declares is a link that can never come up — and nothing
                    # about the configuration says so.
                    "ring1_addr": "10.10.0.1",
                    "quorum_votes": 1,
                },
                {"node": SECONDARY, "nodeid": 2, "ring0_addr": "192.168.68.159", "quorum_votes": 1},
            ]
        ),
        "/cluster/config/totem": (
            {}
            if single
            else {
                "cluster_name": CLUSTER,
                "config_version": "2",
                "transport": "knet",
                "secauth": "on",
                # No ``two_node`` and no ``wait_for_all``: the reference
                # cluster's quorum margin is zero and this is where that shows.
                "link_mode": "passive",
            }
        ),
        "/cluster/log": _CLUSTER_LOG,
        "/cluster/ha/resources": [] if single else _HA_RESOURCES,
        "/cluster/ha/groups": [],
        "/cluster/ha/status/manager_status": {} if single else {"quorum": {"quorate": "1"}},
        "/cluster/ha/status/current": [] if single else _HA_STATUS,
        "/cluster/backup": _BACKUP_JOBS,
        f"/nodes/{PRIMARY}/status": {
            "uptime": 813_600,
            "loadavg": ["1.42", "1.31", "1.20"],
            "cpu": 0.63,
            "cpuinfo": {"cpus": 8, "model": "Intel(R) Core(TM) i7"},
            "memory": {"total": 33_284_000_000, "used": 19_304_000_000},
            "swap": {"total": 8_589_934_592, "used": 1_073_741_824},
            "rootfs": {"total": 103_079_215_104, "used": 34_016_000_000},
            "kversion": "Linux 7.0.14-8-pve",
            "pveversion": f"pve-manager/{VERSION}",
        },
        f"/nodes/{SECONDARY}/status": {
            "uptime": 813_600,
            "loadavg": ["0.31", "0.28", "0.24"],
            "cpu": 0.09,
            "cpuinfo": {"cpus": 12, "model": "AMD Ryzen 5"},
            "memory": {"total": 67_355_000_000, "used": 34_351_000_000},
            "swap": {"total": 8_589_934_592, "used": 0},
            "rootfs": {"total": 103_079_215_104, "used": 82_463_000_000},
            "kversion": "Linux 7.0.14-8-pve",
            "pveversion": f"pve-manager/{VERSION}",
        },
        f"/nodes/{SECONDARY}/storage": [
            {
                "storage": "local-lvm",
                "type": "lvmthin",
                "active": 1,
                "enabled": 1,
                "shared": 0,
                "total": 375_700_000_000,
                "used": 317_300_000_000,
                "content": "images,rootdir",
            },
            {
                "storage": "TeraChad",
                "type": "cifs",
                "active": 1,
                "enabled": 1,
                "shared": 1,
                "total": 8_001_000_000_000,
                "used": 7_654_000_000_000,
                "content": "backup,iso",
            },
        ],
        f"/nodes/{SECONDARY}/storage/local-lvm/status": {
            "type": "lvmthin",
            "total": 375_700_000_000,
            "used": 317_300_000_000,
            "avail": 58_400_000_000,
            "active": 1,
        },
        f"/nodes/{SECONDARY}/storage/local-lvm/content": [
            {"volid": "local-lvm:vm-100-disk-0", "size": 107_374_182_400, "vmid": 100},
            # A disk belonging to a guest the cluster no longer has. Proxmox
            # keeps the volume when a guest is removed with its disks retained,
            # and nothing afterwards ever mentions it again.
            {"volid": "local-lvm:vm-129-disk-0", "size": 34_359_738_368, "vmid": 129},
        ],
        f"/nodes/{SECONDARY}/disks/list": [
            {
                "devpath": "/dev/nvme0n1",
                "size": 1_000_204_886_016,
                "model": "Samsung SSD 980 PRO",
                "serial": "S5GXNF0R123456",
                "type": "nvme",
                "health": "PASSED",
                "wearout": 97,
                # What Proxmox says the disk is being used for. It names the
                # technology and not the pool, which is why a disk-to-pool map
                # is only completable for ZFS.
                "used": "LVM",
            },
            {
                "devpath": "/dev/sda",
                "size": 4_000_787_030_016,
                "model": "WDC WD40EFRX",
                "serial": "WD-WCC7K1234567",
                "type": "hdd",
                "health": "PASSED" if not degraded else "FAILED",
                "wearout": "N/A",
                "used": "ZFS",
            },
        ],
        f"/nodes/{SECONDARY}/disks/lvmthin": _LVM_THIN,
        f"/nodes/{SECONDARY}/disks/lvm": _LVM_VOLUMES,
        # Neither reference node has ZFS. An empty list is the reading, and it is
        # emphatically not a failed one — the question is inapplicable here.
        f"/nodes/{SECONDARY}/disks/zfs": [],
        f"/nodes/{PRIMARY}/disks/zfs": [],
        f"/nodes/{SECONDARY}/tasks": [
            {
                "upid": "UPID:pve02:0000B1C4:0511D6A2:68943A10:vzdump:100:root@pam:",
                "type": "vzdump",
                "status": "OK",
                "starttime": 1_754_800_000,
                "endtime": 1_754_801_800,
                "node": SECONDARY,
                "user": "root@pam",
            },
            {
                "upid": "UPID:pve02:0000B1C5:0511D6A3:68943A11:vzdump:129:root@pam:",
                "type": "vzdump",
                "status": "job errors",
                "starttime": 1_754_802_000,
                "endtime": 1_754_802_400,
                "node": SECONDARY,
                "user": "root@pam",
            },
        ],
        f"/nodes/{SECONDARY}/replication": [],
        f"/nodes/{SECONDARY}/certificates/info": [
            {
                "filename": "pveproxy-ssl.pem",
                "fingerprint": "3B:1F:CD:9A",
                "notafter": 1_785_000_000,
                "subject": f"CN={SECONDARY}",
            }
        ],
        f"/nodes/{SECONDARY}/apt/update": [
            {"Package": "proxmox-kernel-7.0", "Version": "7.0.14-9", "Priority": "optional"},
            {"Package": "jq", "Version": "1.7.1-4", "Priority": "security"},
        ],
        f"/nodes/{SECONDARY}/network": [
            {
                "iface": "vmbr0",
                "type": "bridge",
                "active": 1,
                "autostart": 1,
                "cidr": "192.168.68.159/24",
            },
            {"iface": "enp1s0", "type": "eth", "active": 1, "autostart": 1},
        ],
        f"/nodes/{SECONDARY}/time": {"timezone": "Europe/Lisbon", "time": 1_754_803_000},
        # Corosync tolerates very little clock difference between members. In the
        # degraded corpus the primary is 47 seconds ahead, which is far past what
        # the token protocol survives and is invisible to every other reading.
        f"/nodes/{PRIMARY}/time": {
            "timezone": "Europe/Lisbon",
            "time": 1_754_803_047 if degraded else 1_754_803_000,
        },
        f"/nodes/{PRIMARY}/network": [
            {
                "iface": "vmbr0",
                "type": "bridge",
                "active": 1,
                "autostart": 1,
                "cidr": "192.168.68.149/24",
            },
        ],
        f"/nodes/{PRIMARY}/storage": [
            {
                "storage": "local-lvm",
                "type": "lvmthin",
                "active": 1,
                "enabled": 1,
                "shared": 0,
                "total": 375_700_000_000,
                "used": 210_400_000_000,
                "content": "images,rootdir",
            },
            {
                # An NFS mount that is down. Proxmox answers with the datastore
                # still declared and its status unknown, which is not a fill
                # level and is not an empty datastore either.
                "storage": "externo-nfs-pve01",
                "type": "nfs",
                "active": 0,
                "enabled": 1,
                "shared": 1,
                "status": "unknown",
                "content": "backup",
            },
        ],
        f"/nodes/{PRIMARY}/storage/local-lvm/content": [
            {"volid": "local-lvm:vm-9000-disk-0", "size": 137_438_953_472, "vmid": 9000},
            {"volid": "local-lvm:vm-137-disk-0", "size": 34_359_738_368, "vmid": 137},
        ],
        f"/nodes/{PRIMARY}/disks/lvmthin": [_LVM_THIN[0]],
        f"/nodes/{PRIMARY}/disks/lvm": [_LVM_VOLUMES[3]],
        f"/nodes/{PRIMARY}/disks/list": [
            {
                "devpath": "/dev/sdb",
                "size": 512_110_190_592,
                "model": "Crucial CT500MX500",
                "serial": "2019E2B1F4C7",
                "type": "ssd",
                "health": "PASSED",
                "wearout": 88,
            },
        ],
        f"/nodes/{PRIMARY}/tasks": [
            {
                "upid": "UPID:pve01:0000C201:05120000:68943B00:vzdump:9000:root@pam:",
                "type": "vzdump",
                "status": "job errors",
                "starttime": 1_754_700_000,
                "endtime": 1_754_700_600,
                "node": PRIMARY,
                "user": "root@pam",
            },
        ],
        f"/nodes/{PRIMARY}/replication": [],
        # The cluster-wide datastore definitions: which nodes may see each one.
        "/storage": list(_STORAGE_CONFIGURATION),
        "/access/permissions": {
            "/": {"Sys.Audit": 1, "Datastore.Audit": 1},
            "/vms": {"VM.Audit": 1},
            "/storage": {"Datastore.Audit": 1},
            "/nodes": {"Sys.Audit": 1},
        },
    }

    # Per-guest reads, for the two kinds. Only the guests the tests name.
    responses[f"/nodes/{SECONDARY}/lxc/100/status/current"] = {
        "status": "running",
        "name": "plex",
        "vmid": 100,
        "cpus": 4,
        "maxmem": 4294967296,
        "mem": 3_221_225_472,
        "maxdisk": 107374182400,
        "disk": 106_900_000_000,
        "uptime": 813_244,
        "ha": {"managed": 0},
    }
    responses[f"/nodes/{SECONDARY}/lxc/100/config"] = {
        "hostname": "plex",
        "cores": 4,
        "memory": 4096,
        "ostype": "debian",
        "rootfs": "data-pool:vm-100-disk-0,size=100G",
        # NFR-003: a cloud-init style secret sitting in guest configuration.
        "password": "hunter2-the-operators-actual-password",
        "ssh-public-keys": (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n"
            "-----END OPENSSH PRIVATE KEY-----"
        ),
    }
    responses[f"/nodes/{SECONDARY}/lxc/100/snapshot"] = [
        {"name": "current", "digest": "abc"},
        {"name": "before-upgrade", "snaptime": 1_754_000_000},
    ]
    responses[f"/nodes/{SECONDARY}/lxc/100/pending"] = [
        {"key": "memory", "value": "4096", "pending": "8192"},
    ]
    responses[f"/nodes/{SECONDARY}/lxc/100/status/tasks"] = []
    responses[f"/nodes/{PRIMARY}/qemu/9000/status/current"] = {
        "status": "stopped",
        "name": "windows-lab",
        "vmid": 9000,
        "cpus": 4,
        "maxmem": 8589934592,
        "mem": 0,
        "maxdisk": 137438953472,
        "uptime": 0,
        "lock": "backup",
        "ha": {"managed": 1},
        "agent": 1,
    }
    responses[f"/nodes/{PRIMARY}/qemu/9000/config"] = {
        "name": "windows-lab",
        "cores": 4,
        "memory": 8192,
        "ostype": "win11",
        "boot": "order=scsi0",
        "scsi0": "local-lvm:vm-9000-disk-0,size=128G",
        # A second disk on the share whose mount is down. This is why the guest
        # will not start, and nothing about the guest itself says so.
        "scsi1": "externo-nfs-pve01:vm-9000-disk-1,size=500G",
        "agent": "1",
        "cipassword": "another-secret-nobody-should-store",
    }
    responses[f"/nodes/{PRIMARY}/qemu/9000/snapshot"] = [{"name": "current", "digest": "def"}]
    responses[f"/nodes/{PRIMARY}/qemu/9000/pending"] = []
    responses[f"/nodes/{PRIMARY}/qemu/9000/agent/get-fsinfo"] = {
        "result": [
            {"mountpoint": "C:\\", "total-bytes": 137438953472, "used-bytes": 68_000_000_000}
        ]
    }
    # The guest Proxmox reports with no name at all, on the primary node.
    responses[f"/nodes/{PRIMARY}/lxc/137/status/current"] = {
        "status": "running",
        "vmid": 137,
        "cpus": 2,
        "maxmem": 2_147_483_648,
        "mem": 900_000_000,
        "maxdisk": 34_359_738_368,
        "disk": 21_000_000_000,
        "uptime": 604_800,
        "ha": {"managed": 0},
    }
    responses[f"/nodes/{PRIMARY}/lxc/137/config"] = {
        "cores": 2,
        "memory": 2048,
        "ostype": "debian",
        "rootfs": "local-lvm:vm-137-disk-0,size=32G",
    }
    responses[f"/nodes/{PRIMARY}/lxc/137/snapshot"] = []
    responses[f"/nodes/{PRIMARY}/lxc/137/status/tasks"] = []
    responses[f"/nodes/{PRIMARY}/qemu/9000/status/tasks"] = [
        {
            "upid": "UPID:pve01:0000C201:05120000:68943B00:qmstart:9000:root@pam:",
            "type": "qmstart",
            "status": "storage 'externo-nfs-pve01' is not online",
            "starttime": 1_754_802_500,
            "endtime": 1_754_802_501,
            "node": PRIMARY,
            "user": "root@pam",
        },
    ]

    # The two containers whose own volumes are near full, and which carry the
    # cluster's prior stall postmortems. Read per guest rather than from the
    # cluster list, because a guest question is what the per-guest reads are for.
    for vmid, name, memory, used in (
        (115, "adguard", 536_870_912, 515_000_000),
        (140, "unbound", 268_435_456, 96_000_000),
    ):
        responses[f"/nodes/{SECONDARY}/lxc/{vmid}/status/current"] = {
            "status": "running",
            "name": name,
            "vmid": vmid,
            "cpus": 1,
            "maxmem": memory,
            "mem": used,
            "maxdisk": 8_589_934_592,
            "disk": 8_100_000_000,
            "uptime": 813_190,
            "ha": {"managed": 0},
        }
        responses[f"/nodes/{SECONDARY}/lxc/{vmid}/config"] = {
            "hostname": name,
            "cores": 1,
            "memory": memory // (1024 * 1024),
            "ostype": "debian",
            "rootfs": f"local-lvm:vm-{vmid}-disk-0,size=8G",
        }
        responses[f"/nodes/{SECONDARY}/lxc/{vmid}/snapshot"] = []
        responses[f"/nodes/{SECONDARY}/lxc/{vmid}/status/tasks"] = []

    # SMART, per device. Proxmox takes the disk as a query parameter, so these are
    # keyed with it: a corpus keyed by path alone would answer every disk with one
    # drive's attributes, which is exactly the reading this tool exists to make.
    for node, devices in ((PRIMARY, ("/dev/sdb",)), (SECONDARY, ("/dev/nvme0n1", "/dev/sda"))):
        for device in devices:
            report = _SMART.get(device, {"health": "PASSED", "type": "ata", "attributes": []})
            responses[f"/nodes/{node}/disks/smart?disk={device}"] = report

    responses[f"/nodes/{SECONDARY}/storage/TeraChad/content"] = [
        {
            "volid": "TeraChad:backup/vzdump-lxc-100-2025_08_09-07_00_02.tar.zst",
            "size": 42_000_000_000,
            "vmid": 100,
            "ctime": 1_754_800_000,
            "format": "tar.zst",
            "content": "backup",
        },
        {
            # A backup of a guest the cluster no longer has. Its disk is an
            # orphan and its backup is retention nobody is watching.
            "volid": "TeraChad:backup/vzdump-lxc-129-2025_07_02-07_00_02.tar.zst",
            "size": 18_000_000_000,
            "vmid": 129,
            "ctime": 1_751_400_000,
            "format": "tar.zst",
            "content": "backup",
        },
    ]

    if degraded:
        responses[f"/nodes/{SECONDARY}/disks/lvmthin"] = [
            {**_LVM_THIN[0], "metadata_percent": 96.10},
            _LVM_THIN[1],
        ]

    if down:
        responses.pop(f"/nodes/{SECONDARY}/status", None)
        responses.pop(f"/nodes/{SECONDARY}/storage", None)
        # Its clock goes with it. A node left out of a skew calculation because
        # nobody could read it is a node the calculation is quietly wrong about.
        responses.pop(f"/nodes/{SECONDARY}/time", None)

    return RecordedCluster(state=state, responses=responses)


#: Every state, so a test can sweep the corpus rather than name four of five.
STATES: Final[tuple[ClusterState, ...]] = tuple(ClusterState)


# --- Driving a client from the corpus -----------------------------------------


@dataclass(slots=True)
class RecordedProxmox:
    """The recorded cluster behind the proxy transport, for a whole suite.

    The corpus is keyed by path and, where Proxmox takes one, by query — SMART is
    read per disk, and a transport that dropped the parameter would answer every
    drive with one drive's attributes. Lookup tries the fuller key first so a
    recording that does not need the parameter still resolves.

    ``unreachable`` is the state every investigation tool has to survive: not an
    empty answer, but no answer at all. It raises the error a refused connection
    raises, which is what the client's failover exhausts and what a tool then
    has to report as something it could not determine.
    """

    cluster: RecordedCluster
    unreachable: bool = False
    offline_hosts: frozenset[str] = frozenset()
    seen: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Answer ``request`` from the recording, or say why it cannot be answered."""
        split = urlsplit(request.url)
        host = split.hostname or ""
        self.hosts.append(host)
        if self.unreachable or host in self.offline_hosts:
            raise IntegrationError(
                f"connection refused by {host}",
                integration=INTEGRATION,
                reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
            )

        path = split.path.removeprefix(API_BASE)
        # Unencoded, so a recording is keyed the way an operator would write it:
        # ``/disks/smart?disk=/dev/sda`` rather than ``disk=%2Fdev%2Fsda``.
        query = "&".join(f"{key}={value}" for key, value in parse_qsl(split.query))
        keyed = f"{path}?{query}" if query else path
        self.seen.append(keyed)
        for candidate in (keyed, path):
            try:
                payload = self.cluster.payload(candidate)
            except KeyError:
                continue
            body = json.dumps({"data": payload}).encode("utf-8")
            return OutboundResponse(200, {"content-type": "application/json"}, body)
        return OutboundResponse(NODE_UNREACHABLE, {}, b"595 no route to host")


#: Proxmox's own status for "the node that owns this endpoint is not answering".
#: A cluster with a node down answers cluster-wide reads normally and answers
#: that node's own reads with this, which is why it is a reading about the node
#: rather than an error about the request.
NODE_UNREACHABLE: Final = 595


#: The two addresses every test's client is given. Both, always, because the
#: property that matters is that reads keep working when the node named in the
#: configuration is the one that died.
ENDPOINTS: Final[tuple[str, ...]] = ("pve01.acme.example", "pve02.acme.example")


def transport_for(
    state: ClusterState = ClusterState.HEALTHY,
    *,
    unreachable: bool = False,
    responses: Mapping[str, Any] | None = None,
    offline: frozenset[str] = frozenset(),
) -> RecordedProxmox:
    """Return the recorded cluster behind a transport.

    ``responses`` overlays the corpus, which is how a test supplies the one
    degraded reading it is about — a ZFS pool on a cluster that has none, a
    thousand snapshots — without a sixth recorded state that every other test
    would then have to sweep.
    """
    corpus = recorded(state)
    if responses:
        corpus = RecordedCluster(state=state, responses={**corpus.responses, **responses})
    return RecordedProxmox(cluster=corpus, unreachable=unreachable, offline_hosts=offline)


def client_for(
    state: ClusterState = ClusterState.HEALTHY,
    *,
    unreachable: bool = False,
    responses: Mapping[str, Any] | None = None,
    endpoints: Sequence[str] = ENDPOINTS,
    offline: frozenset[str] = frozenset(),
) -> tuple[ProxmoxClient, RecordedProxmox]:
    """Return a Proxmox client reading ``state``, and the transport behind it."""
    transport = transport_for(state, unreachable=unreachable, responses=responses, offline=offline)
    client = ProxmoxClient(
        transport=transport,
        context=RequestContext(org_id="acme", team_id="homelab", capability="proxmox_probe"),
        endpoints=tuple(endpoints),
        retry=RetryPolicy(max_attempts=1),
    )
    return client, transport


@dataclass(frozen=True, slots=True)
class _ImpatientAccess(IntegrationAccess):
    """Integration access whose clients do not wait between retries.

    A capability builds its own client and takes no retry policy, so the only
    place a test can shorten the schedule is here. What is being exercised below
    is the tool's behaviour when a node does not answer, not the base client's
    backoff — which has its own tests — and paying the real schedule once per
    tool turns a fast suite into a slow one for no additional assurance.
    """

    def client[Client: IntegrationClient](
        self,
        factory: Callable[..., Client],
        *,
        capability: str,
        **options: Any,
    ) -> Client:
        """Return a client of ``factory``'s type that retries once and waits never.

        ``IntegrationAccess.client`` is called explicitly rather than through a
        zero-argument ``super()``: ``@dataclass(slots=True)`` builds a *new*
        class object, so the compiler's ``__class__`` cell points at the one
        before decoration and the implicit form raises.
        """
        return IntegrationAccess.client(
            self, factory, capability=capability, retry=RetryPolicy(max_attempts=1), **options
        )


@contextmanager
def investigating(
    state: ClusterState = ClusterState.HEALTHY,
    *,
    unreachable: bool = False,
    responses: Mapping[str, Any] | None = None,
) -> Iterator[RecordedProxmox]:
    """Bind this process's integration access onto the recorded cluster.

    What a *tool* test needs, as opposed to a client test: a capability builds
    its own client from the process binding and takes no transport, which is the
    arrangement that stops a tool inventing its own tenant scope. Restoring the
    previous binding on the way out is what keeps one test's cluster out of the
    next one's.
    """
    transport = transport_for(state, unreachable=unreachable, responses=responses)
    previous = bind(_ImpatientAccess(transport=transport, org_id="acme", team_id="homelab"))
    try:
        yield transport
    finally:
        restore(previous)


__all__ = [
    "CLUSTER",
    "NODE_UNREACHABLE",
    "PRIMARY",
    "SECONDARY",
    "STATES",
    "VERSION",
    "ZFS_POOLS",
    "ZFS_POOL_DETAIL",
    "ClusterState",
    "ENDPOINTS",
    "RecordedCluster",
    "RecordedProxmox",
    "client_for",
    "data",
    "investigating",
    "recorded",
    "transport_for",
]
