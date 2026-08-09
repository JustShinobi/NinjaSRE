"""Whether a guest could move, and — when it could not — exactly what stops it.

"Migrate it to the other node" is the first suggestion anybody makes about a
node that is in trouble, and on a small cluster it is usually impossible for a
reason nobody checked. Five of them, each a different conversation:

**Quorum.** Without it nothing moves anywhere, so this is checked first and
makes every other blocker downstream of itself.

**Local disks.** A guest on node-local storage cannot move without copying its
disk, and the datastore's declaration is what says so — a datastore restricted to
one node is a guest pinned to that node.

**Datastore availability.** A shared datastore the target cannot currently reach
is the same blocker wearing different clothes, and it is invisible in the
configuration because the configuration is correct.

**Passthrough devices.** A PCI device or a USB dongle exists in one machine.
Nothing about the guest's configuration says which machine, and the migration
fails at the far end.

**Target resources.** A node with less free memory than the guest is configured
for will take the migration and then fail to start it.

So the answer is per target node, with the reasons attached, rather than a
boolean about the guest.

Source of truth: the cluster's quorum state and membership, the guest's
configuration, the cluster's datastore declarations, and each candidate node's
status and datastore list.
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
from integrations.proxmox.investigation import report
from integrations.proxmox.schema import INTEGRATION
from integrations.proxmox.tools.guest_start_diagnosis import DISK_KEYS, PASSTHROUGH_KEYS

TOOL_NAME = "proxmox_migration_feasibility"

_USE_CASES = (
    "checking whether a guest could actually move before proposing that it does",
    "finding out which node could receive a guest and which could not, with the reason",
    "seeing that a guest is pinned by node-local storage rather than by anything about itself",
)

_ANTI_EXAMPLES = (
    "performing a migration — nothing here writes",
    "which datastores exist where, which proxmox_datastore_availability reads",
    "why the guest will not start where it is, which proxmox_guest_start_diagnosis answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox migration feasibility",
    description=(
        "Return whether a Proxmox guest could move and, per candidate node, exactly what "
        "prevents it: no quorum, a node-local disk, a datastore the target cannot reach, a "
        "passthrough device that exists in one machine, or not enough memory on the target. "
        "Moving the guest is the first thing anybody suggests and on a small cluster it is "
        "usually impossible for a reason nobody checked."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "guest", "migration", "storage", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_migration_feasibility(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return whether guest ``vmid`` could leave ``node``, and what stops it."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        status = await client.cluster_status()
        guest = await client.guest_status(node, vmid, kind=kind)
        configuration = await client.guest_configuration(node, vmid, kind=kind)
        declared = await client.storage_configuration()
        candidates = [member.name for member in status.members if member.name != node]
        elsewhere = {
            name: (await client.node_status(name), await client.node_storage(name))
            for name in candidates
        }
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    quorate = status.quorate or not status.is_clustered
    disks = _disks(configuration)
    passthrough = sorted(
        str(key)
        for key in configuration
        if any(str(key).startswith(prefix) for prefix in PASSTHROUGH_KEYS)
    )
    restrictions = {
        str(row.get("storage", "")): _restriction(row) for row in declared if row.get("storage")
    }

    blockers: list[dict[str, str]] = []
    if not quorate:
        blockers.append(
            {
                "kind": "quorum",
                "reason": (
                    "the cluster has no quorum, so no guest can be migrated anywhere until it "
                    "returns — every blocker below is downstream of this one"
                ),
            }
        )
    for store in sorted(set(disks.values())):
        allowed = restrictions.get(store)
        if allowed:
            blockers.append(
                {
                    "kind": "local-disk",
                    "reason": (
                        f"this guest has a disk on {store}, which the cluster declares only for "
                        f"{', '.join(allowed)} — the guest is pinned to that node until the "
                        f"disk is copied"
                    ),
                }
            )
    if passthrough:
        blockers.append(
            {
                "kind": "passthrough",
                "reason": (
                    f"this guest declares {', '.join(passthrough)}, which is hardware in one "
                    f"machine; the migration would be accepted and would fail at the far end"
                ),
            }
        )

    targets = [
        _target(name, reading, stores, disks=disks, restrictions=restrictions, guest=guest)
        for name, (reading, stores) in sorted(elsewhere.items())
    ]
    receivable = [target for target in targets if target["can_receive"]]
    can_migrate = quorate and not passthrough and bool(receivable)

    value: dict[str, Any] = {
        "node": node,
        "guest": vmid,
        "kind": kind,
        "can_migrate": can_migrate,
        "blockers": blockers,
        "targets": targets,
        "disks": [{"key": key, "datastore": store} for key, store in sorted(disks.items())],
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, vmid, kind, can_migrate, blockers, receivable),
        reference=f"proxmox:migration:{node}/{kind}/{vmid}",
        evidence_type=EvidenceType.ANALYSIS,
    )


def _disks(configuration: Mapping[str, Any]) -> dict[str, str]:
    """Return which datastore each configured disk is on, keyed by its config key."""
    found: dict[str, str] = {}
    for key, raw in configuration.items():
        name = str(key)
        if not any(name.startswith(prefix) for prefix in DISK_KEYS):
            continue
        value = str(raw)
        if ":" in value:
            found[name] = value.split(":", 1)[0]
    return found


def _restriction(row: Mapping[str, Any]) -> list[str]:
    """Return the nodes a datastore is restricted to, empty meaning every node."""
    text = str(row.get("nodes", "") or "")
    return [part.strip() for part in text.split(",") if part.strip()]


def _target(
    name: str,
    reading: Any,
    stores: Any,
    *,
    disks: dict[str, str],
    restrictions: dict[str, list[str]],
    guest: Any,
) -> dict[str, Any]:
    """Return whether one node could receive the guest, and why it could not."""
    reasons: list[str] = []
    reachable = {store.name for store in stores if store.is_available}
    for store in sorted(set(disks.values())):
        allowed = restrictions.get(store)
        if allowed and name not in allowed:
            reasons.append(f"{store} is not declared for {name}")
        elif store not in reachable:
            reasons.append(f"{name} cannot currently reach {store}")

    if not reading.available:
        reasons.append(f"{name} did not answer, so its free memory is unknown")
    else:
        status = reading.require()
        free = status.memory_total_bytes - status.memory_used_bytes
        if free < guest.memory_bytes:
            reasons.append(
                f"{name} has {free} bytes free and the guest is configured for {guest.memory_bytes}"
            )

    return {"node": name, "can_receive": not reasons, "reasons": reasons}


def _summary(
    node: str,
    vmid: int,
    kind: str,
    can_migrate: bool,
    blockers: list[dict[str, str]],
    receivable: list[dict[str, Any]],
) -> str:
    """Return the one line a conclusion can be checked against."""
    if can_migrate:
        return (
            f"{kind}/{vmid} can move from {node} to "
            f"{', '.join(target['node'] for target in receivable)}"
        )
    if not blockers:
        return f"{kind}/{vmid} cannot move from {node}: no other node could receive it"
    return f"{kind}/{vmid} cannot move from {node}: {blockers[0]['reason']}"


__all__ = ["TOOL_NAME", "proxmox_migration_feasibility"]
