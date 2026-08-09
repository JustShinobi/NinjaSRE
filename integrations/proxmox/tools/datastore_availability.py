"""Which datastores each node may see, and which it can actually reach.

Two different facts, and a guest's ability to move depends on both. A datastore
is *declared* for a set of nodes in the cluster's own configuration — an empty
restriction means every node — and it is *reachable* only if the node's mount is
currently up. A guest cannot migrate to a node that its disk's datastore is not
declared on, however healthy both nodes are; and it cannot start on a node whose
mount for that datastore has failed, however correct the declaration is.

The third state is the one that reads as the other two. Proxmox reports a share
whose mount is down as ``unknown``, which is neither available nor a fill level
and is emphatically not an empty datastore. Two of the reference cluster's
datastores are in exactly that state, and anything reading the fill percentage
sees a comfortable zero.

Source of truth: ``/storage`` for the declarations, and each node's own
``/storage`` for what it can currently reach.
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
from integrations.proxmox.investigation import report
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_datastore_availability"

_USE_CASES = (
    "checking whether a guest could move to a node before proposing that it does",
    "finding a datastore reporting unknown, which is a failed mount rather than an empty share",
    "seeing which datastores are node-local and therefore pin the guests on them in place",
)

_ANTI_EXAMPLES = (
    "mounting a datastore or changing its node restriction — nothing here writes",
    "how full each datastore is, which proxmox_storage_pressure reads",
    "whether a particular guest can migrate, which proxmox_migration_feasibility answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox datastore availability",
    description=(
        "Return which datastores each Proxmox node is declared for and which it can currently "
        "reach, keeping the two apart. A datastore reporting unknown is a mount that failed, "
        "not an empty share and not a fill level, and a guest cannot move to a node its "
        "disk's datastore is not declared on however healthy both nodes are."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "storage", "datastore", "migration", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_datastore_availability() -> CapabilityResult:
    """Return each node's declared and reachable datastores, separately."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        declared = await client.storage_configuration()
        status = await client.cluster_status()
        names = [member.name for member in status.members]
        seen = {node: await client.node_storage(node) for node in names}
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    datastores = [
        {
            "name": str(row.get("storage", "")),
            "type": str(row.get("type", "")),
            "shared": bool(int(row.get("shared", 0) or 0)),
            "nodes": _restriction(row),
            "node_local": bool(_restriction(row)),
        }
        for row in declared
        if row.get("storage")
    ]

    nodes = [_node(name, datastores, seen.get(name, ())) for name in names]
    value: dict[str, Any] = {"datastores": datastores, "nodes": nodes}
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(nodes),
        reference=f"proxmox:datastores:{status.name or 'standalone'}",
        evidence_type=EvidenceType.CONFIGURATION,
    )


def _restriction(row: Any) -> list[str]:
    """Return the nodes a datastore is restricted to, empty meaning every node."""
    text = str(row.get("nodes", "") or "")
    return [part.strip() for part in text.split(",") if part.strip()]


def _node(name: str, datastores: list[dict[str, Any]], seen: Any) -> dict[str, Any]:
    """Return what one node is declared for, what it reaches, and what it does not."""
    declared = [
        store["name"] for store in datastores if not store["nodes"] or name in store["nodes"]
    ]
    reachable = {store.name for store in seen if store.is_available}
    unreachable = sorted(set(declared) - reachable)
    return {
        "node": name,
        "declared": sorted(declared),
        "available": sorted(set(declared) & reachable),
        "unreachable": unreachable,
        "not_declared": sorted(
            store["name"] for store in datastores if store["name"] not in declared
        ),
    }


def _summary(nodes: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    broken = [
        f"{node['node']} cannot reach {', '.join(node['unreachable'])}"
        for node in nodes
        if node["unreachable"]
    ]
    if broken:
        return (
            "; ".join(broken)
            + " — a datastore that is declared and unreachable pins every guest whose disk is "
            "on it"
        )
    return f"every datastore declared for each of the {len(nodes)} node(s) is reachable from it"


__all__ = ["TOOL_NAME", "proxmox_datastore_availability"]
