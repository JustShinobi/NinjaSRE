"""What high availability is managing, what it wants, and whether it is about to fence.

A managed resource has two states and they are frequently different: what the
manager has been asked for, and what the resource is actually doing. A tool that
reported one would report a guest as ``started`` while its node was being reset.

Fencing is the reading that matters and it is not published as a field. Two
conditions produce it, and they need saying apart:

**It has occurred.** A resource whose current state is ``fence`` — the manager
has decided a node is unresponsive and is resetting it. Guests on that node are
being stopped by a watchdog rather than by anything graceful.

**It is imminent.** The cluster has lost quorum and there are managed resources.
The manager cannot act without quorum, and the watchdog on each node does not
wait for the manager: a node that cannot reach the cluster resets itself after
its timer expires whether or not anybody has decided anything. On a two-node
cluster this is the ordinary consequence of losing one node, and it is the
reason "just force quorum" is the most expensive plausible first move there is.

Source of truth: ``/cluster/ha/resources``, ``/cluster/ha/groups``,
``/cluster/ha/status/current``, and the cluster's quorum state.
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
from integrations.proxmox.models import ClusterStatus, HighAvailabilityState
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_ha_state"

#: The states a managed resource is in while the manager is resetting its node,
#: or has given up on it. Both mean a guest is being stopped by a watchdog.
FENCING_STATES: frozenset[str] = frozenset({"fence", "error"})

_USE_CASES = (
    "finding out whether high availability is about to reset a node",
    "seeing what state the manager wants a guest in against what it is actually in",
    "checking which guests high availability manages before proposing to stop one",
)

_ANTI_EXAMPLES = (
    "why a guest will not start, which proxmox_guest_start_diagnosis answers",
    "moving a resource or changing its group — nothing here writes",
    "whether the cluster is quorate, which proxmox_quorum_status answers directly",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox high availability state",
    description=(
        "Return which Proxmox guests high availability manages, the state the manager wants "
        "each in against the state it is actually in, which node is manager, and whether "
        "fencing has occurred or is imminent. A cluster that has lost quorum with managed "
        "resources is a cluster whose watchdogs are counting down, which no field says."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "cluster", "high-availability", "fencing", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_ha_state() -> CapabilityResult:
    """Return managed resources, manager status, and the fencing position."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        state = await client.high_availability()
        status = await client.cluster_status()
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    resources = _resources(state)
    fencing = _fencing(resources, state, status)
    value: dict[str, Any] = {
        "resources": resources,
        "groups": [
            {"group": str(row.get("group", "")), "nodes": str(row.get("nodes", ""))}
            for row in state.groups
        ],
        "manager": {
            "node": state.manager_node,
            "status": state.manager_status,
            "local_managers": dict(state.lrm_states),
        },
        "fencing": fencing,
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(resources, fencing, state),
        reference=f"proxmox:ha:{status.name or 'standalone'}",
        evidence_type=EvidenceType.CONFIGURATION,
    )


def _resources(state: HighAvailabilityState) -> list[dict[str, Any]]:
    """Return each managed resource with both of its states, never one."""
    current_states = {
        str(row.get("sid", "")): row for row in state.services if str(row.get("sid", ""))
    }
    declared = {str(row.get("sid", "")): row for row in state.resources if str(row.get("sid", ""))}
    for sid, row in current_states.items():
        declared.setdefault(sid, row)

    found: list[dict[str, Any]] = []
    for sid, row in sorted(declared.items()):
        live = current_states.get(sid, row)
        found.append(
            {
                "sid": sid,
                "node": str(live.get("node", row.get("node", ""))),
                "group": str(row.get("group", "")),
                "requested_state": str(live.get("request_state", row.get("state", ""))),
                "current_state": str(live.get("crm_state", live.get("state", ""))),
                "max_restart": int(row.get("max_restart", 0) or 0),
            }
        )
    return found


def _fencing(
    resources: list[dict[str, Any]],
    state: HighAvailabilityState,
    status: ClusterStatus,
) -> dict[str, Any]:
    """Return whether a node is being reset, or is about to be."""
    fencing = [
        entry["sid"] for entry in resources if entry["current_state"].lower() in FENCING_STATES
    ]
    imminent = bool(resources) and status.is_clustered and not status.quorate
    reason = ""
    if fencing:
        reason = (
            f"the manager has moved {', '.join(fencing)} to a fencing state, which means the "
            f"node carrying them is being reset rather than stopped"
        )
    elif imminent:
        reason = (
            "the cluster has no quorum and high availability is managing resources. The "
            "manager cannot act without quorum and the per-node watchdog does not wait for "
            "it, so a node that stays unquorate resets itself when its timer expires"
        )
    return {
        "occurred": bool(fencing),
        "imminent": imminent,
        "resources": fencing,
        "mode": state.fencing_mode,
        "reason": reason,
    }


def _summary(
    resources: list[dict[str, Any]],
    fencing: dict[str, Any],
    state: HighAvailabilityState,
) -> str:
    """Return the one line a conclusion can be checked against."""
    if not resources:
        return (
            "no resource is managed by high availability, so nothing here will be fenced or "
            "restarted automatically"
        )
    if fencing["occurred"]:
        return f"FENCING: {fencing['reason']}"
    if fencing["imminent"]:
        return f"fencing is imminent: {fencing['reason']}"
    disagreeing = [
        entry["sid"] for entry in resources if entry["requested_state"] != entry["current_state"]
    ]
    if disagreeing:
        return (
            f"{len(resources)} managed resource(s); {', '.join(disagreeing)} are not in the "
            f"state the manager asked for"
        )
    return (
        f"{len(resources)} managed resource(s), all in the state the manager asked for; "
        f"{state.manager_node or 'no node'} is manager"
    )


__all__ = ["FENCING_STATES", "TOOL_NAME", "proxmox_ha_state"]
