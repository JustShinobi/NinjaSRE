"""Disks that belong to no guest, and the guest each one used to belong to.

Proxmox keeps a volume when a guest is destroyed with its disks retained, and
nothing afterwards ever mentions it again. It occupies its datastore, it is
counted in the datastore's fill, and no inventory of guests reaches it — so a
datastore that is filling for no visible reason is very often filling with
disks whose guests were deleted months ago.

The reading that makes this safe is the **former owner**. A volume named
``vm-129-disk-0`` on a cluster with no guest 129 is an orphan; a volume named
``vm-100-disk-0`` on a cluster that still has guest 100 is a disk in use, and
the two look identical to anything matching on names alone. VMIDs are also
reused freely after a guest is destroyed, which is the second reason the
existing-guest check has to be made against the live resource list rather than
against a memory of it.

Source of truth: the cluster resource list for the guests, and each node's
datastore contents for the volumes.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import bounded, report
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_orphaned_volumes"

_USE_CASES = (
    "finding out why a datastore is filling when no guest on it has grown",
    "listing disks left behind by guests that were destroyed with their disks retained",
    "checking whether a volume is genuinely unused before anybody proposes removing it",
)

_ANTI_EXAMPLES = (
    "deleting a volume — nothing here writes, and this is the tool whose output looks most "
    "like a delete list",
    "how full a datastore is, which proxmox_storage_pressure reads",
    "what a backup contains, which is a restore rather than a read",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox orphaned volumes",
    description=(
        "Return the disk volumes on a Proxmox cluster that belong to no existing guest, each "
        "with the guest id it was named for and the space it occupies. Proxmox keeps a volume "
        "when a guest is destroyed with its disks retained, and nothing afterwards mentions "
        "it again while it still counts towards the datastore's fill."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "storage", "orphan", "disk", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_orphaned_volumes() -> CapabilityResult:
    """Return every volume whose guest no longer exists, with what it occupies."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        resources = await client.cluster_resources()
        guests = {
            int(row.get("vmid", 0) or 0) for row in resources if row.get("type") in {"lxc", "qemu"}
        }
        nodes = sorted({str(row.get("node", "")) for row in resources if row.get("type") == "node"})
        found: list[dict[str, Any]] = []
        for node in nodes:
            for store in await client.node_storage(node):
                if not store.is_available:
                    continue
                for row in await client.datastore_contents(node, store.name, content="images"):
                    entry = _volume(node, store.name, row)
                    if entry is not None and entry["former_guest"] not in guests:
                        found.append(entry)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    orphans, bound = bounded(
        found, ranked_by="the space each volume occupies", key=lambda entry: entry["size_bytes"]
    )
    value: dict[str, Any] = {
        "orphans": list(orphans),
        "reclaimable_bytes": sum(entry["size_bytes"] for entry in found),
        "guests_seen": len(guests),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(found, value),
        reference="proxmox:orphans",
        evidence_type=EvidenceType.CONFIGURATION,
        bounds=(("orphans", bound),),
    )


def _volume(node: str, datastore: str, row: dict[str, Any] | Any) -> dict[str, Any] | None:
    """Return one volume record, or ``None`` when the row is not a guest disk."""
    volid = str(row.get("volid", ""))
    content = str(row.get("content", ""))
    if not volid or content == "backup" or "/backup/" in volid:
        return None
    vmid = int(row.get("vmid", 0) or 0)
    if not vmid:
        return None
    return {
        "volid": volid,
        "node": node,
        "datastore": datastore,
        "former_guest": vmid,
        "size_bytes": int(row.get("size", 0) or 0),
        "protects": (
            f"nothing running: guest {vmid} is not in the cluster's resource list, so this "
            f"volume is the disk of a guest that no longer exists"
        ),
    }


def _summary(found: list[dict[str, Any]], value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not found:
        return "every volume on this cluster belongs to a guest that still exists"
    return (
        f"{len(found)} volume(s) belong to no existing guest and occupy "
        f"{value['reclaimable_bytes']} bytes: "
        + ", ".join(f"{entry['volid']} (guest {entry['former_guest']})" for entry in found[:5])
    )


__all__ = ["TOOL_NAME", "proxmox_orphaned_volumes"]
