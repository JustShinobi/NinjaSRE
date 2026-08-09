"""What each drive's firmware says, and the attributes that say it first.

A SMART verdict is the firmware's opinion of itself and it is the last thing to
change. ``PASSED`` while the reallocated sector count has climbed to 184 and
twenty-four sectors are pending is the ordinary way a disk fails: the verdict
flips days or hours before the drive stops, and the counters moved months
earlier. So the attributes that predict are reported apart from the verdict, and
a drive whose verdict passes while they climb is called out by name.

The second half of the answer is what each disk *backs*, because a failing drive
matters exactly as much as what is on it. That map is only completable where the
technology publishes it: ZFS names its devices, and LVM does not — Proxmox
reports a disk as being "used for LVM" without ever saying which volume group.
Where the map cannot be completed the disk says so, rather than being reported
as backing nothing.

Source of truth: ``/nodes/<node>/disks/list``, ``/disks/smart`` per device, and
the ZFS pool device trees where there are any.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import (
    PREDICTIVE_SMART_ATTRIBUTES,
    Undetermined,
    report,
)
from integrations.proxmox.models import PhysicalDisk
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_disk_health"

_USE_CASES = (
    "finding a drive whose SMART verdict still passes while its pending sectors climb",
    "checking which pool or datastore a failing disk is underneath before planning anything",
    "reading the wear indicator on solid-state drives that back a hypervisor's guests",
)

_ANTI_EXAMPLES = (
    "replacing a disk or starting a self-test — nothing here writes",
    "how full a datastore is, which proxmox_storage_pressure reads",
    "ZFS pool state, which proxmox_zfs_health reads",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox disk health",
    description=(
        "Return each physical disk's SMART verdict, the attributes that predict a failure "
        "before the verdict changes, and which ZFS pool it backs. A drive reporting PASSED "
        "with a climbing reallocated-sector count is the ordinary way a disk fails, and the "
        "verdict is the last field to move."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "disk", "smart", "storage", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_disk_health(node: str) -> CapabilityResult:
    """Return each disk on ``node`` with its predictive attributes and what it backs."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        disks = await client.node_disks(node)
        backing = await _backing_map(client, node)
        reports: list[dict[str, Any]] = []
        for disk in disks:
            smart = await client.disk_smart(node, disk.device)
            if not smart.available:
                holes.append(
                    Undetermined(
                        question=f"the SMART attributes of {disk.device} on {node}",
                        reason=smart.unavailable_reason,
                        published_by=smart.published_by,
                    )
                )
            backs = sorted(backing.get(_leaf(disk.device), ()))
            if not backs:
                holes.append(_unmapped(node, disk))
            reports.append(_disk(disk, smart.or_else({}), backs))
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    value: dict[str, Any] = {"node": node, "disks": reports}
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, reports),
        reference=f"proxmox:disks:{node}",
        undetermined=holes,
    )


async def _backing_map(client: ProxmoxClient, node: str) -> dict[str, set[str]]:
    """Return which pool each device backs, for the technologies that publish it.

    ZFS names its leaf devices, so its map is complete. Nothing else does, which
    is why this returns what it can rather than a map with invented entries.
    """
    found: dict[str, set[str]] = {}
    listing = await client.zfs_pools(node)
    for row in listing.or_else(()):
        pool = str(row.get("name", ""))
        detail = await client.zfs_pool_detail(node, pool)
        for device in _leaves(detail.or_else({})):
            found.setdefault(device, set()).add(pool)
    return found


def _leaves(detail: Mapping[str, Any]) -> list[str]:
    """Return every leaf device name in a ZFS pool's tree."""
    names: list[str] = []

    def descend(entry: Mapping[str, Any]) -> None:
        children = entry.get("children") or []
        if not children and entry.get("name"):
            names.append(str(entry["name"]))
        for child in children:
            if isinstance(child, dict):
                descend(child)

    for child in detail.get("children") or []:
        if isinstance(child, dict):
            descend(child)
    return names


def _leaf(device: str) -> str:
    """Return the bare device name ZFS uses, from the path Proxmox reports."""
    return device.rsplit("/", 1)[-1]


def _unmapped(node: str, disk: PhysicalDisk) -> Undetermined:
    """Return the hole a disk with no discoverable backing leaves."""
    return Undetermined(
        question=f"which pool or datastore {disk.device} on {node} backs",
        reason=(
            f"Proxmox reports it as used for {disk.used_for or 'something it does not name'} "
            f"and never says which volume group or datastore. Only ZFS publishes its device "
            f"list, so the map is completable there and nowhere else."
        ),
        published_by="pvs and lsblk, on the node",
    )


def _disk(disk: PhysicalDisk, smart: Mapping[str, Any], backs: list[str]) -> dict[str, Any]:
    """Return one disk's reading, with the verdict and the attributes kept apart."""
    attributes = [
        row
        for row in smart.get("attributes", []) or []
        if isinstance(row, dict) and str(row.get("name", "")) in PREDICTIVE_SMART_ATTRIBUTES
    ]
    predictive = [
        {
            "name": str(row.get("name", "")),
            "raw": str(row.get("raw", "")),
            "value": int(row.get("value", 0) or 0),
            "threshold": int(row.get("threshold", 0) or 0),
        }
        for row in attributes
    ]
    return {
        "device": disk.device,
        "model": disk.model,
        "serial": disk.serial,
        "size_bytes": disk.size_bytes,
        "disk_type": disk.disk_type,
        "smart_health": disk.smart_health,
        "smart_passed": disk.smart_passed,
        "wearout": disk.wearout,
        "used_for": disk.used_for,
        "backs": backs,
        "predictive_attributes": predictive,
        "predicts_failure": _predicts(predictive),
    }


def _predicts(attributes: list[dict[str, Any]]) -> bool:
    """Return whether any predictive attribute has moved off zero or past its threshold.

    Raw counts rather than the normalised value, because the normalised value is
    what the verdict is computed from and is therefore the thing that has not
    moved yet.
    """
    for entry in attributes:
        if entry["name"] in {"Media_Wearout_Indicator", "Percent_Lifetime_Remain"}:
            if entry["threshold"] and entry["value"] <= entry["threshold"]:
                return True
            continue
        raw = entry["raw"].strip()
        if raw.isdigit() and int(raw) > 0:
            return True
    return False


def _summary(node: str, disks: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    failing = [disk["device"] for disk in disks if not disk["smart_passed"]]
    predicting = [
        disk["device"] for disk in disks if disk["predicts_failure"] and disk["smart_passed"]
    ]
    parts: list[str] = []
    if failing:
        parts.append(f"SMART has already failed on {', '.join(failing)}")
    if predicting:
        parts.append(
            f"{', '.join(predicting)} still report PASSED while attributes that predict "
            f"failure have moved off zero"
        )
    if not parts:
        return f"{node}: {len(disks)} disk(s), none of them predicting a failure"
    return f"{node}: " + "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_disk_health"]
