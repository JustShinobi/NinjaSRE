"""The whole reference cluster, at the size it actually is, with its inventory.

The recorded corpus beside this one is about *readings* — a thin pool near its
metadata ceiling, a node that is down, a cluster that lost quorum — and it
carries a handful of guests, because a reading does not get truer with fifty
more of them.

This one is about *shape*: two nodes, fifty-seven containers, forty-nine of them
running, and seven declared networks. Those numbers are what an operator
recognises as their own cluster, and they are what the acceptance criteria are
written in. A fixture that carried five containers would prove the sweep works
and nothing about whether the estate this feature builds is the estate the
operator has.

**The counts are declared once, here, and everything else is derived.** The
per-zone figures (infra 25, apps 21, dmz 7, ci 2, backup 1, vk8s 1) are the
declaration; the guests, their addresses, the cluster resource list, the
per-guest configurations and the inventory documents are all generated from it.
A test asserting "infra holds 25" and a fixture generating 24 cannot happen,
because they are the same number.

**Everything is deterministic and nothing reads a clock.** Which guests are
stopped is an explicit list rather than every seventh; addresses are assigned in
VMID order. Two runs of this suite produce identical bytes, which is the whole
reason the numbers can be asserted at all.

**The declared inventory disagrees with the cluster on purpose.** One container
is declared and not reported (deleted, and the file has not caught up) and one
is reported and not declared (created by hand). Both are divergences, and a
fixture where the two sides agreed perfectly would let the divergence path rot
undetected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from tests.support.proxmox import CLUSTER, PRIMARY, SECONDARY, ClusterState, transport_for

#: The seven networks the cluster is divided into, in the order the zone file
#: declares them. ``mgmt`` holds the two hypervisor nodes and no guests, which
#: is why the guest counts sum to fifty-seven across six zones and the estate
#: still reports seven.
ZONES: Final[tuple[tuple[str, str], ...]] = (
    ("mgmt", "10.20.10.0/24"),
    ("infra", "10.20.20.0/24"),
    ("apps", "10.20.30.0/24"),
    ("dmz", "10.20.40.0/24"),
    ("ci", "10.20.50.0/24"),
    ("backup", "10.20.60.0/24"),
    ("vk8s", "10.20.70.0/24"),
)

#: How many containers each zone holds. The declaration everything else is
#: derived from, and the numbers the acceptance criteria are written in.
ZONE_GUESTS: Final[tuple[tuple[str, int], ...]] = (
    ("infra", 25),
    ("apps", 21),
    ("dmz", 7),
    ("ci", 2),
    ("backup", 1),
    ("vk8s", 1),
)

#: Fifty-seven, which is what the sum of the above has to be.
TOTAL_GUESTS: Final = sum(count for _, count in ZONE_GUESTS)

#: The eight that are not running. Named rather than computed, so "forty-nine
#: running" is a fact about this fixture rather than an arithmetic accident that
#: changes when somebody reorders a loop.
STOPPED_VMIDS: Final[frozenset[int]] = frozenset({103, 111, 128, 133, 140, 148, 153, 155})

RUNNING_GUESTS: Final = TOTAL_GUESTS - len(STOPPED_VMIDS)

#: The addresses the two nodes answer on, both inside ``mgmt``.
NODE_ADDRESSES: Final[Mapping[str, str]] = {
    PRIMARY: "10.20.10.11",
    SECONDARY: "10.20.10.12",
}

#: Declared in the inventory and not reported by the cluster: deleted, and the
#: file has not caught up. Exactly the case the specification calls a finding.
GONE_VMID: Final = 900

#: Reported by the cluster and not declared: created by hand, so nothing says
#: what it is for.
UNDECLARED_VMID: Final = 156

_FIRST_VMID: Final = 100

#: Which criticality each zone's containers are declared with. A zone is not a
#: criticality — the dmz holds the public edge and the ci zone holds throwaway
#: runners — and collapsing the two would make the enrichment look like a
#: relabelling of the zone map.
_ZONE_CRITICALITY: Final[Mapping[str, str]] = {
    "infra": "high",
    "apps": "medium",
    "dmz": "high",
    "ci": "low",
    "backup": "medium",
    "vk8s": "medium",
}


@dataclass(frozen=True, slots=True)
class Guest:
    """One container in the reference cluster, and everything about it."""

    vmid: int
    name: str
    node: str
    zone: str
    address: str

    @property
    def running(self) -> bool:
        """Return whether this guest is up in the fixture."""
        return self.vmid not in STOPPED_VMIDS

    @property
    def status(self) -> str:
        """Return the word Proxmox reports for it."""
        return "running" if self.running else "stopped"

    @property
    def correlation_key(self) -> str:
        """Return the value the API and the declared inventory are matched on."""
        return f"{CLUSTER}/lxc/{self.vmid}"


def guests() -> tuple[Guest, ...]:
    """Return the fifty-seven containers, derived from the zone declaration."""
    built: list[Guest] = []
    vmid = _FIRST_VMID
    for zone, count in ZONE_GUESTS:
        network = dict(ZONES)[zone].split("/", 1)[0].rsplit(".", 1)[0]
        for index in range(count):
            built.append(
                Guest(
                    vmid=vmid,
                    name=f"{zone}-{index + 1:02d}",
                    node=PRIMARY if vmid % 2 == 0 else SECONDARY,
                    zone=zone,
                    address=f"{network}.{index + 10}",
                )
            )
            vmid += 1
    return tuple(built)


GUESTS: Final[tuple[Guest, ...]] = guests()


def zone_counts() -> dict[str, int]:
    """Return how many containers each zone holds, as the fixture built them."""
    counted: dict[str, int] = {}
    for guest in GUESTS:
        counted[guest.zone] = counted.get(guest.zone, 0) + 1
    return counted


# --- the API responses --------------------------------------------------------


def _cluster_status() -> list[dict[str, Any]]:
    """Return the membership view, with both nodes on the management network."""
    return [
        {
            "type": "cluster",
            "id": "cluster",
            "name": CLUSTER,
            "version": 2,
            "nodes": 2,
            "quorate": 1,
        },
        {
            "type": "node",
            "id": f"node/{PRIMARY}",
            "name": PRIMARY,
            "online": 1,
            "local": 0,
            "ip": NODE_ADDRESSES[PRIMARY],
            "nodeid": 1,
        },
        {
            "type": "node",
            "id": f"node/{SECONDARY}",
            "name": SECONDARY,
            "online": 1,
            "local": 1,
            "ip": NODE_ADDRESSES[SECONDARY],
            "nodeid": 2,
        },
    ]


def _cluster_resources(stopped: frozenset[int]) -> list[dict[str, Any]]:
    """Return the cluster-wide list: two nodes and fifty-seven containers."""
    rows: list[dict[str, Any]] = [
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
            "status": "online",
            "maxcpu": 12,
            "maxmem": 67_355_000_000,
            "uptime": 813_600,
        },
    ]
    rows.extend(
        {
            "id": f"lxc/{guest.vmid}",
            "type": "lxc",
            "vmid": guest.vmid,
            "name": guest.name,
            "node": guest.node,
            "status": "stopped" if guest.vmid in stopped else "running",
            "maxcpu": 2,
            "maxmem": 2_147_483_648,
            "maxdisk": 21_474_836_480,
            "uptime": 0 if guest.vmid in stopped else 813_244,
        }
        for guest in GUESTS
    )
    return rows


def _guest_configuration(guest: Guest) -> dict[str, Any]:
    """Return one container's configuration, with the address on its network line."""
    return {
        "arch": "amd64",
        "cores": 2,
        "hostname": guest.name,
        "memory": 2048,
        "ostype": "debian",
        "net0": (
            f"name=eth0,bridge=vmbr0,gw=10.20.{guest.address.split('.')[2]}.1,"
            f"hwaddr=BC:24:11:00:{guest.vmid:02X}:01,ip={guest.address}/24,type=veth"
        ),
        "rootfs": f"local-lvm:vm-{guest.vmid}-disk-0,size=20G",
        # Proxmox writes the creation time into the guest's own notes, and the
        # estate uses it to keep a reused VMID from inheriting a dead guest's
        # history. Fixed here rather than derived from the clock.
        "description": f"created 2026-01-{(guest.vmid % 28) + 1:02d}",
    }


def responses(*, stopped: frozenset[int] = STOPPED_VMIDS) -> dict[str, Any]:
    """Return the overlay that turns the recorded corpus into this cluster.

    ``stopped`` is a parameter so a second sweep can stop one more container and
    the estate can be asked whether it recorded a transition — which is a
    different question from whether it rewrote the resource.
    """
    overlay: dict[str, Any] = {
        "/cluster/status": _cluster_status(),
        "/cluster/resources": _cluster_resources(stopped),
    }
    for guest in GUESTS:
        overlay[f"/nodes/{guest.node}/lxc/{guest.vmid}/config"] = _guest_configuration(guest)
    return overlay


def cluster_transport(*, stopped: frozenset[int] = STOPPED_VMIDS) -> Any:
    """Return a transport answering for the whole reference cluster."""
    return transport_for(ClusterState.HEALTHY, responses=responses(stopped=stopped))


# --- the declared inventory ---------------------------------------------------


def zones_document() -> str:
    """Return ``zones.yaml`` as the repository publishes it."""
    lines = ["zones:"]
    for name, cidr in ZONES:
        lines.append(f"  - name: {name}")
        lines.append(f"    cidr: {cidr}")
        lines.append(f"    gateway: {cidr.split('/', 1)[0].rsplit('.', 1)[0]}.1")
        if name == "vk8s":
            # The one number a postmortem put in this file, and the reason the
            # zone exists in the declaration at all.
            lines.append("    mtu: 1450")
    return "\n".join(lines) + "\n"


def nodes_document() -> str:
    """Return ``nodes.yaml``: both hypervisors, declared as critical."""
    lines = ["nodes:"]
    for node in (PRIMARY, SECONDARY):
        lines.extend(
            [
                f"  - name: {node}",
                "    criticality: high",
                "    tier: hypervisor",
                "    owner: platform",
            ]
        )
    return "\n".join(lines) + "\n"


def cts_document() -> str:
    """Return ``cts.yaml``: every container but one, plus one that is gone."""
    lines = ["containers:"]
    for guest in GUESTS:
        if guest.vmid == UNDECLARED_VMID:
            continue
        lines.extend(
            [
                f"  - vmid: {guest.vmid}",
                f"    name: {guest.name}",
                f"    node: {guest.node}",
                f"    criticality: {_ZONE_CRITICALITY[guest.zone]}",
                f"    tier: {guest.zone}",
                "    owner: platform",
            ]
        )
    lines.extend(
        [
            f"  - vmid: {GONE_VMID}",
            "    name: retired-runner",
            f"    node: {PRIMARY}",
            "    criticality: low",
            "    tier: ci",
        ]
    )
    return "\n".join(lines) + "\n"


def vms_document() -> str:
    """Return ``vms.yaml``. The reference cluster runs containers and no full guests."""
    return "virtual_machines: []\n"


def services_document() -> str:
    """Return ``services.yaml``: the domains the edge answers on."""
    edge = [guest for guest in GUESTS if guest.zone == "dmz"][:3]
    lines = ["services:"]
    for guest in edge:
        lines.extend(
            [
                f"  - name: {guest.name}",
                f"    domain: {guest.name}.example.internal",
                f"    vmid: {guest.vmid}",
            ]
        )
    return "\n".join(lines) + "\n"


def inventory_documents() -> dict[str, str]:
    """Return the five documents the ingestion reads, keyed by their base name."""
    return {
        "zones": zones_document(),
        "nodes": nodes_document(),
        "cts": cts_document(),
        "vms": vms_document(),
        "services": services_document(),
    }


def write_inventory(root: Any) -> Any:
    """Write the inventory tree under ``root`` and return ``root``."""
    directory = root / "inventory" / "cluster"
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in inventory_documents().items():
        (directory / f"{name}.yaml").write_text(body, encoding="utf-8")
    return root


__all__ = [
    "GONE_VMID",
    "GUESTS",
    "NODE_ADDRESSES",
    "RUNNING_GUESTS",
    "STOPPED_VMIDS",
    "TOTAL_GUESTS",
    "UNDECLARED_VMID",
    "ZONES",
    "ZONE_GUESTS",
    "Guest",
    "cluster_transport",
    "inventory_documents",
    "responses",
    "write_inventory",
    "zone_counts",
]
