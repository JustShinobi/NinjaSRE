"""Where the pressure on a guest actually is, when the symptom is the same either way.

A guest that is slow, that cannot write, or that is being killed looks the same
whether the cause is inside it or underneath it — and the remedies are on
different machines. Two attributions, made explicitly rather than left to be
inferred:

**Memory.** A node that is swapping and a guest that is at its own ceiling both
produce a guest that stalls. Add memory to the guest and a swapping host gets
worse; add memory to the host and a guest at its own limit is unchanged. So the
node's ratio and the guest's are read together and one of them is named.

**Storage.** "The agent says the disk is full" and "the host's storage is full"
are different sentences and only one of them is fixed inside the guest. Where a
guest agent answers, its filesystems are compared against the datastores the
guest's disks are on, and the attribution is stated. Where the agent does not
answer, that is reported as a fact about the agent — not as a fact about the
guest, and not as a filesystem that is fine.

Two readings are named and not made. **Ballooning** is reported from the guest's
configuration, which says what was asked for rather than what is currently
reclaimed. **CPU steal** is not published by the Proxmox API at all; it is
visible inside the guest and nowhere else, and an investigation told nothing
about steal will attribute a stolen CPU to the guest's own load every time.

Source of truth: the guest's status and configuration, its agent where there is
one, and the node's status and datastore list.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import GUEST_KINDS, ProxmoxClient
from integrations.proxmox.investigation import Undetermined, report
from integrations.proxmox.models import Datastore, GuestStatus
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_guest_pressure"

#: Above this proportion of its own memory, a guest is close enough to its
#: ceiling that its own allocator is the constraint.
GUEST_MEMORY_PRESSURE_RATIO: Final = 0.90

#: Above this proportion of the node's memory, or this much swap in use, the
#: host is the constraint whatever the guest inside it is doing.
HOST_MEMORY_PRESSURE_RATIO: Final = 0.90
HOST_SWAP_PRESSURE_RATIO: Final = 0.25

#: Above this proportion, a filesystem — the host's or the guest's — is full
#: enough that writes are already failing or about to.
FULL_RATIO: Final = 0.95

_USE_CASES = (
    "telling host memory pressure from a guest that is at its own memory ceiling",
    "telling a guest filesystem that is full from a host datastore that is full",
    "checking what a guest agent reports about the guest's own disks before blaming the host",
)

_ANTI_EXAMPLES = (
    "resizing a guest's memory or its disk — nothing here writes",
    "why a stopped guest will not start, which proxmox_guest_start_diagnosis answers",
    "cluster-wide storage pressure, which proxmox_storage_pressure reads per node",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox guest pressure",
    description=(
        "Return where the pressure on a Proxmox guest is: host memory against guest memory, "
        "the node's swap, ballooning, and the guest's own filesystems against the datastores "
        "its disks are on — with the attribution stated. A stalling guest looks the same "
        "whether the cause is inside it or underneath it, and the two are fixed on different "
        "machines. CPU steal is named as unreadable rather than omitted."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "guest", "memory", "storage", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_guest_pressure(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return whether the pressure on guest ``vmid`` is the host's or its own."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        guest = await client.guest_status(node, vmid, kind=kind)
        configuration = await client.guest_configuration(node, vmid, kind=kind)
        node_status = await client.node_status(node)
        datastores = await client.node_storage(node)
        agent = await client.guest_agent_filesystems(node, vmid) if kind == GUEST_KINDS[1] else None
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    if agent is None:
        holes.append(
            Undetermined(
                question=f"what the guest agent inside {kind}/{vmid} says about its filesystems",
                reason=(
                    "a container has no QEMU guest agent, so the only filesystem reading "
                    "available is the host's view of its volume"
                ),
                published_by="qemu-guest-agent, which containers do not run",
            )
        )
    elif not agent.available:
        holes.append(
            Undetermined(
                question=f"what the guest agent inside {kind}/{vmid} says about its filesystems",
                reason=agent.unavailable_reason,
                published_by=agent.published_by,
            )
        )

    holes.append(
        Undetermined(
            question=f"how much CPU steal {kind}/{vmid} is experiencing",
            reason=(
                "the Proxmox API does not publish steal time. It is visible inside the guest "
                "and nowhere else, and an investigation with no steal reading attributes a "
                "stolen CPU to the guest's own load every time."
            ),
            published_by="the guest's own /proc/stat, or a node exporter inside it",
        )
    )

    memory = _memory(guest, node_status)
    storage, storage_hole = _storage(guest, configuration, datastores, agent)
    holes.append(storage_hole)

    value: dict[str, Any] = {
        "node": node,
        "guest": vmid,
        "kind": kind,
        "status": guest.status,
        "memory": memory,
        "storage": storage,
        "ballooning": _ballooning(configuration, guest),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, vmid, kind, memory, storage),
        reference=f"proxmox:pressure:{node}/{kind}/{vmid}",
        evidence_type=EvidenceType.ANALYSIS,
        undetermined=holes,
    )


def _memory(guest: GuestStatus, node_status: Any) -> dict[str, Any]:
    """Return the guest's and the node's memory positions, and which is the constraint."""
    guest_ratio = guest.memory_used_bytes / guest.memory_bytes if guest.memory_bytes else 0.0
    guest_pressed = guest_ratio >= GUEST_MEMORY_PRESSURE_RATIO

    if not node_status.available:
        return {
            "guest_ratio": round(guest_ratio, 4),
            "guest_under_pressure": guest_pressed,
            "host_known": False,
            "host_under_pressure": False,
            "host_ratio": 0.0,
            "host_swap_ratio": 0.0,
            "attribution": "guest" if guest_pressed else "neither",
        }

    status = node_status.require()
    host_pressed = (
        status.memory_ratio >= HOST_MEMORY_PRESSURE_RATIO
        or status.swap_ratio >= HOST_SWAP_PRESSURE_RATIO
    )
    return {
        "guest_ratio": round(guest_ratio, 4),
        "guest_under_pressure": guest_pressed,
        "host_known": True,
        "host_ratio": round(status.memory_ratio, 4),
        "host_swap_ratio": round(status.swap_ratio, 4),
        "host_under_pressure": host_pressed,
        "attribution": _attribute(host_pressed, guest_pressed),
    }


def _storage(
    guest: GuestStatus,
    configuration: Mapping[str, Any],
    datastores: tuple[Datastore, ...],
    agent: Any,
) -> tuple[dict[str, Any], Undetermined | None]:
    """Return the host's and the guest's filesystem positions, and which is full."""
    wanted = {
        str(raw).split(":", 1)[0]
        for key, raw in configuration.items()
        if ":" in str(raw) and str(key)[0].isalpha() and "size=" in str(raw)
    }
    by_name = {store.name: store for store in datastores}
    backing = [by_name[name] for name in sorted(wanted) if name in by_name]
    unknown = sorted(wanted - set(by_name))

    host_full = [store.name for store in backing if store.used_ratio >= FULL_RATIO]
    filesystems = [
        {
            "mountpoint": str(row.get("mountpoint", "")),
            "total_bytes": int(row.get("total-bytes", 0) or 0),
            "used_bytes": int(row.get("used-bytes", 0) or 0),
            "used_ratio": round(
                int(row.get("used-bytes", 0) or 0) / int(row.get("total-bytes", 1) or 1), 4
            ),
        }
        for row in (agent.or_else(()) if agent is not None else ())
    ]
    guest_full = [
        str(entry["mountpoint"])
        for entry in filesystems
        if float(str(entry["used_ratio"])) >= FULL_RATIO
    ]

    host_known = bool(backing)
    guest_known = bool(filesystems)
    attribution = "undetermined"
    if host_full and guest_full:
        attribution = "both"
    elif host_full:
        attribution = "host"
    elif guest_full:
        attribution = "guest"
    elif host_known and guest_known:
        attribution = "neither"

    hole = None
    if unknown:
        hole = Undetermined(
            question=(
                f"how full the datastore(s) {', '.join(unknown)} behind {guest.kind}/"
                f"{guest.vmid} are"
            ),
            reason=(
                "this node's datastore list does not include them, so the host side of the "
                "comparison is incomplete and 'the host is fine' is not available as a "
                "conclusion"
            ),
            published_by="the node that does declare that datastore",
        )
    return (
        {
            "host_datastores": [
                {"name": store.name, "used_ratio": round(store.used_ratio, 4)} for store in backing
            ],
            "host_datastores_full": host_full,
            "guest_filesystems": filesystems,
            "guest_filesystems_full": guest_full,
            "attribution": attribution,
        },
        hole,
    )


def _ballooning(configuration: Mapping[str, Any], guest: GuestStatus) -> dict[str, Any]:
    """Return what ballooning was configured for, which is not what it is reclaiming."""
    declared = configuration.get("balloon")
    return {
        "configured": declared is not None,
        "minimum_bytes": int(str(declared or 0) or 0) * 1024 * 1024,
        "maximum_bytes": guest.memory_bytes,
        "note": (
            "this is what ballooning was configured for. How much the balloon is currently "
            "reclaiming is not published per guest, so a guest whose usable memory has been "
            "taken back reads as a guest that is simply using less"
        ),
    }


def _attribute(host: bool, guest: bool) -> str:
    """Return which side owns the pressure when both are known."""
    if host and guest:
        return "both"
    if host:
        return "host"
    if guest:
        return "guest"
    return "neither"


def _summary(
    node: str, vmid: int, kind: str, memory: dict[str, Any], storage: dict[str, Any]
) -> str:
    """Return the one line a conclusion can be checked against."""
    parts: list[str] = []
    if memory["attribution"] == "host":
        parts.append(
            f"the memory pressure is the HOST's — {node} is at "
            f"{memory['host_ratio']:.0%} memory with {memory['host_swap_ratio']:.0%} swap in "
            f"use, and adding memory to the guest would make it worse"
        )
    elif memory["attribution"] == "guest":
        parts.append(
            f"the memory pressure is the GUEST's — it is at {memory['guest_ratio']:.0%} of its "
            f"own ceiling on a node that is comfortable"
        )
    elif memory["attribution"] == "both":
        parts.append("both the host and the guest are short of memory")

    if storage["attribution"] == "host":
        parts.append(
            f"the storage that is full is the HOST's: {', '.join(storage['host_datastores_full'])}"
        )
    elif storage["attribution"] == "guest":
        parts.append(
            f"the storage that is full is the GUEST's own filesystem: "
            f"{', '.join(storage['guest_filesystems_full'])}, on a host with room"
        )
    elif storage["attribution"] == "both":
        parts.append("the host's datastore and the guest's own filesystem are both full")

    if not parts:
        return f"{kind}/{vmid} on {node} is under no memory or storage pressure that is readable"
    return f"{kind}/{vmid} on {node}: " + "; ".join(parts)


__all__ = [
    "FULL_RATIO",
    "GUEST_MEMORY_PRESSURE_RATIO",
    "HOST_MEMORY_PRESSURE_RATIO",
    "HOST_SWAP_PRESSURE_RATIO",
    "TOOL_NAME",
    "proxmox_guest_pressure",
]
