"""How full things are, at the three levels that fail independently.

A datastore's fill percentage is the number everybody watches and it is the least
useful of the three. On the reference cluster ``local-lvm`` reports 84% while the
container inside it sits at 99.6% of its own thin volume — the guest is about to
see write failures and the datastore looks fine. Meanwhile the thin *pool* under
both of them has a metadata percentage that has nothing to do with either: a pool
that exhausts its metadata stops accepting writes entirely while its data figure
is comfortable.

So this reads all three and says which one is under pressure:

- **datastores**, with the ones reporting ``unknown`` called out separately —
  that is what Proxmox says about a share whose mount is down, and it is not a
  fill level at all;
- **thin pools**, data and metadata reported apart;
- **thin volumes**, each guest's own ceiling.

Source of truth: the cluster resource list for datastores, and per node
``/disks/lvmthin`` and ``/disks/lvm`` for the two below it.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_storage_pressure"

#: Above this a datastore is worth reporting even when nothing has failed yet.
#: A judgement rather than a fact, which is why it is named.
DATASTORE_PRESSURE_RATIO = 0.90

_USE_CASES = (
    "finding out whether a guest that cannot write is out of its own volume rather than "
    "out of datastore space",
    "checking a thin pool's metadata, which stops writes while its data figure looks fine",
    "listing the datastores a node currently cannot reach at all",
)

_ANTI_EXAMPLES = (
    "growing a volume or a pool — nothing here writes",
    "what is inside a backup, which is a datastore-contents question",
    "whether a guest is healthy, which storage pressure is only one cause of",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox storage pressure",
    description=(
        "Return how full a Proxmox node's storage is at the three levels that fail "
        "independently: datastores, LVM-thin pools with data and metadata reported "
        "separately, and each guest's own thin volume. A guest at 99% of its volume while "
        "its datastore reports 84% is the case a datastore threshold cannot see."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "storage", "lvm", "thin", "disk", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_storage_pressure(node: str) -> CapabilityResult:
    """Return the datastores, thin pools and thin volumes on ``node``, with their fill."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        datastores = await client.node_storage(node)
        pools = await client.thin_pools(node)
        volumes = await client.thin_volumes(node)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    value: dict[str, Any] = {
        "node": node,
        "datastores": [
            {
                "name": store.name,
                "status": store.status,
                "used_ratio": round(store.used_ratio, 4),
                "shared": store.shared,
            }
            for store in datastores
        ],
        "unreachable_datastores": [store.name for store in datastores if not store.is_available],
        "thin_pools": [
            {
                "name": pool.name,
                "volume_group": pool.volume_group,
                "data_percent": pool.data_percent,
                "metadata_percent": pool.metadata_percent,
                "metadata_critical": pool.metadata_critical,
            }
            for pool in pools
        ],
        "volumes_near_full": [
            {"name": volume.name, "guest": volume.vmid, "data_percent": volume.data_percent}
            for volume in volumes
            if volume.near_full
        ],
    }
    return CapabilityResult.ok(
        TOOL_NAME,
        value=value,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.METRIC,
                summary=_summary(node, value),
                reference=f"proxmox:storage:{node}",
            ),
        ),
    )


def _summary(node: str, value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    parts: list[str] = []
    unreachable = value["unreachable_datastores"]
    if unreachable:
        parts.append(f"{len(unreachable)} datastore(s) unreachable: {', '.join(unreachable)}")
    full = [
        store["name"]
        for store in value["datastores"]
        if store["used_ratio"] >= DATASTORE_PRESSURE_RATIO
    ]
    if full:
        parts.append(f"datastores over 90%: {', '.join(full)}")
    metadata = [pool["name"] for pool in value["thin_pools"] if pool["metadata_critical"]]
    if metadata:
        parts.append(f"thin pool metadata near exhaustion: {', '.join(metadata)}")
    volumes = value["volumes_near_full"]
    if volumes:
        parts.append(
            "guest volumes near their own ceiling: "
            + ", ".join(f"{item['name']} ({item['data_percent']}%)" for item in volumes)
        )
    return f"{node}: {'; '.join(parts)}" if parts else f"{node}: nothing is under storage pressure"


__all__ = ["DATASTORE_PRESSURE_RATIO", "TOOL_NAME", "proxmox_storage_pressure"]
