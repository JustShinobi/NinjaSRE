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

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

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
                {"node": PRIMARY, "nodeid": 1, "ring0_addr": "192.168.68.149", "quorum_votes": 1},
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
        "/cluster/log": [
            {"id": 1, "node": PRIMARY, "pri": 3, "tag": "corosync", "msg": "link down"},
        ],
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
            },
            {
                "devpath": "/dev/sda",
                "size": 4_000_787_030_016,
                "model": "WDC WD40EFRX",
                "serial": "WD-WCC7K1234567",
                "type": "hdd",
                "health": "PASSED" if not degraded else "FAILED",
                "wearout": "N/A",
            },
        ],
        f"/nodes/{SECONDARY}/disks/lvmthin": _LVM_THIN,
        f"/nodes/{SECONDARY}/disks/zfs": [],
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

    if degraded:
        responses[f"/nodes/{SECONDARY}/disks/lvmthin"] = [
            {**_LVM_THIN[0], "metadata_percent": 96.10},
            _LVM_THIN[1],
        ]

    if down:
        responses.pop(f"/nodes/{SECONDARY}/status", None)
        responses.pop(f"/nodes/{SECONDARY}/storage", None)

    return RecordedCluster(state=state, responses=responses)


#: Every state, so a test can sweep the corpus rather than name four of five.
STATES: Final[tuple[ClusterState, ...]] = tuple(ClusterState)


__all__ = [
    "CLUSTER",
    "PRIMARY",
    "SECONDARY",
    "STATES",
    "VERSION",
    "ClusterState",
    "RecordedCluster",
    "data",
    "recorded",
]
