"""A ZFS pool's health, and the four things its health word does not contain.

``ONLINE`` is the answer to one question and everybody reads it as the answer to
all of them. The four it does not answer:

**Capacity.** Above roughly 80% the allocator changes strategy and write latency
degrades sharply. A pool at 96% is ONLINE, every device is fine, and writes have
already slowed by an order of magnitude. Nothing about the health word contains
this and no alert fires on it.

**Per-device error counts.** A pool stays ONLINE while one leaf device
accumulates checksum errors. The pool's word changes when the device is already
being kicked out; the counter changes months before that.

**Scrub age.** A pool that has never scrubbed has never verified its own data.
ZFS publishes this as English prose and nowhere else, so it is parsed into a
date — and where the prose cannot be parsed, the age is reported as undetermined
rather than invented. A wrong scrub age is indistinguishable from a fresh scrub
that never happened.

**Fragmentation.** Nothing else in the estate reports it, and it is what makes a
pool with free space behave as though it has none.

A node with no ZFS is answered as *inapplicable*. Neither reference node has a
pool, and reporting that as a failure or as an empty result would put a fault
where there is a design decision.

Source of truth: ``/nodes/<node>/disks/zfs`` and each pool's own detail.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import (
    SCRUB_STALE_DAYS,
    ZFS_CAPACITY_DEGRADED_PERCENT,
    Undetermined,
    age_in_days,
    gap,
    report,
    scrub_finished_at,
)
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_zfs_health"

_USE_CASES = (
    "checking whether a ZFS pool that reports ONLINE is above the capacity its write path "
    "degrades at",
    "finding a device accumulating checksum errors inside a pool that still says it is healthy",
    "establishing when a pool last scrubbed, which is the only thing that verifies its data",
)

_ANTI_EXAMPLES = (
    "scrubbing, replacing a device, or expanding a pool — nothing here writes",
    "LVM-thin pools, which proxmox_storage_pressure reads instead",
    "a physical drive's SMART attributes, which proxmox_disk_health reads",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox ZFS pool health",
    description=(
        "Return each ZFS pool's state, per-device error counts, scrub age, fragmentation, and "
        "capacity against the level at which the write path degrades. A pool that reports "
        "ONLINE at 96% capacity with a device quietly accumulating checksum errors is the "
        "case a health word cannot express. A node without ZFS is answered as inapplicable "
        "rather than as empty."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "zfs", "storage", "disk", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_zfs_health(node: str) -> CapabilityResult:
    """Return the ZFS pools on ``node``, or say that the question does not apply."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        listing = await client.zfs_pools(node)
        holes.append(gap(listing, f"which ZFS pools {node} has"))
        pools: list[dict[str, Any]] = []
        for row in listing.or_else(()):
            name = str(row.get("name", ""))
            detail = await client.zfs_pool_detail(node, name)
            holes.append(gap(detail, f"the device tree and scrub state of the pool {name!r}"))
            pool, hole = _pool(row, detail.or_else({}))
            holes.append(hole)
            pools.append(pool)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    value: dict[str, Any] = {
        "node": node,
        "applicable": bool(pools),
        "pools": pools,
        "capacity_threshold_percent": ZFS_CAPACITY_DEGRADED_PERCENT,
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, pools),
        reference=f"proxmox:zfs:{node}",
        undetermined=holes,
    )


def _pool(
    row: Mapping[str, Any], detail: Mapping[str, Any]
) -> tuple[dict[str, Any], Undetermined | None]:
    """Return one pool's reading, and what could not be established about it."""
    name = str(row.get("name", ""))
    size = int(row.get("size", 0) or 0)
    allocated = int(row.get("alloc", 0) or 0)
    capacity = (allocated / size * 100.0) if size else 0.0

    scan = str(detail.get("scan", ""))
    finished = scrub_finished_at(scan)
    hole: Undetermined | None = None
    if scan and finished is None:
        hole = Undetermined(
            question=f"when the pool {name!r} last finished a scrub",
            reason=(
                f"ZFS publishes it only as prose and this deployment's wording did not parse: "
                f"{scan!r}. An invented age would be indistinguishable from a fresh scrub."
            ),
            published_by="zpool status, on the node",
        )
    now = datetime.now(UTC)
    age = age_in_days(finished, now=now) if finished is not None else None

    return (
        {
            "name": name,
            "state": str(detail.get("state", row.get("health", ""))),
            "size_bytes": size,
            "allocated_bytes": allocated,
            "free_bytes": int(row.get("free", 0) or 0),
            "capacity_percent": round(capacity, 2),
            "capacity_degrades_performance": capacity > ZFS_CAPACITY_DEGRADED_PERCENT,
            "fragmentation_percent": int(row.get("frag", 0) or 0),
            "errors": str(detail.get("errors", "")),
            "devices": _devices(detail),
            "scrub": {
                "reported_as": scan,
                "finished_at": finished.isoformat() if finished is not None else "",
                "age_days": round(age, 1) if age is not None else None,
                "stale": bool(age is not None and age > SCRUB_STALE_DAYS),
                "in_progress": "in progress" in scan.lower(),
            },
        },
        hole,
    )


def _devices(detail: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every device in the pool's tree, flattened, leaves marked.

    Flattened because the shape a reader needs is "which device has errors", and
    a nested structure makes that a traversal at every call site — including in
    a model, which is where it goes wrong.
    """
    found: list[dict[str, Any]] = []

    def descend(node: Mapping[str, Any], depth: int) -> None:
        found.append(
            {
                "name": str(node.get("name", "")),
                "state": str(node.get("state", "")),
                "depth": depth,
                "leaf": bool(int(node.get("leaf", 0) or 0)),
                "read_errors": int(node.get("read", 0) or 0),
                "write_errors": int(node.get("write", 0) or 0),
                "checksum_errors": int(node.get("cksum", 0) or 0),
            }
        )
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                descend(child, depth + 1)

    for child in detail.get("children", []) or []:
        if isinstance(child, dict):
            descend(child, 0)
    return found


def _summary(node: str, pools: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not pools:
        return (
            f"{node} has no ZFS pools, so pool health is not applicable here — that is a "
            f"property of how this node was built rather than a failed reading"
        )
    parts: list[str] = []
    for pool in pools:
        if pool["state"].upper() not in {"ONLINE", ""}:
            parts.append(f"{pool['name']} is {pool['state']}")
        if pool["capacity_degrades_performance"]:
            parts.append(
                f"{pool['name']} is at {pool['capacity_percent']}% capacity, past the "
                f"{ZFS_CAPACITY_DEGRADED_PERCENT}% at which the write path degrades while the "
                f"pool still reports {pool['state']}"
            )
        faulty = [
            device["name"]
            for device in pool["devices"]
            if device["read_errors"] or device["write_errors"] or device["checksum_errors"]
        ]
        if faulty:
            parts.append(f"{pool['name']} has errors on {', '.join(faulty)}")
        if pool["scrub"]["stale"]:
            parts.append(f"{pool['name']} last scrubbed {pool['scrub']['age_days']} days ago")
    if not parts:
        return f"{node}: {len(pools)} ZFS pool(s), none of them under capacity or error pressure"
    return f"{node}: " + "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_zfs_health"]
