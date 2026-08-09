"""Why a guest will not start, considered in the order the causes invalidate each other.

Six things stop a Proxmox guest starting and they are not independent. A cluster
without quorum makes every other finding downstream of itself — nothing can be
started anywhere, so the guest's own state is not the answer whatever it says.
A lock stops a start regardless of resources. A datastore the node cannot reach
stops it regardless of the lock. So this returns all six *and* which one is most
likely, ranked by which invalidates which.

The distinction that decides the remedy is the **lock**. A guest showing
``lock: backup`` is either mid-backup — in which case clearing the lock corrupts
the backup — or holding a lock left behind by a task that died, in which case
clearing it is the fix. The guest record does not say which; only the node's task
list does, and only by checking whether a task of that type for that guest is
still running. The task is named and aged so the answer can be checked.

The rest, in the order they are considered: the tasks that already failed and the
vendor's own error text from them; the datastores the guest's disks are on and
whether this node can currently reach them; the node's free memory against what
the guest is configured for; and passthrough devices, which exist on one node's
hardware and nowhere else.

Source of truth: the cluster's quorum state, the guest's status and
configuration, its own and its node's recent tasks, the node's status, and the
node's datastore list.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import MAX_REPORTED_ITEMS, report, seconds_as_phrase
from integrations.proxmox.models import GuestStatus, NodeStatus, TaskRecord
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_guest_start_diagnosis"

#: The configuration keys that name a disk. Proxmox numbers them per bus and a
#: guest may carry several, which is why a guest can be blocked by a datastore
#: nobody associates with it.
DISK_KEYS: tuple[str, ...] = (
    "rootfs",
    "scsi",
    "virtio",
    "ide",
    "sata",
    "efidisk",
    "mp",
    "tpmstate",
)

#: The configuration keys that name hardware belonging to one node and no other.
PASSTHROUGH_KEYS: tuple[str, ...] = ("hostpci", "usb")

_USE_CASES = (
    "finding out why one guest will not start, with the causes ranked rather than listed",
    "telling a lock held by a running backup from one left behind by a task that died",
    "checking whether a guest's disk is on a datastore its node cannot currently reach",
)

_ANTI_EXAMPLES = (
    "starting the guest, or clearing its lock — nothing here writes",
    "whether the guest is under memory pressure while running, which proxmox_guest_pressure "
    "answers",
    "whether the cluster is quorate at all, which proxmox_quorum_status answers directly",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox guest start diagnosis",
    description=(
        "Return why a Proxmox guest will not start: its lock and whether the task holding it "
        "is alive or dead, the errors from its recent failed tasks, the datastores its disks "
        "need and whether this node reaches them, the node's free resources, and passthrough "
        "devices that exist on one node only — with the most likely cause named. A lock held "
        "by a live task and one orphaned by a dead task look identical and have opposite fixes."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.ANALYSIS,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "guest", "lxc", "qemu", "lock", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_guest_start_diagnosis(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return every cause that would stop guest ``vmid`` starting on ``node``, ranked."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        status = await client.cluster_status()
        guest = await client.guest_status(node, vmid, kind=kind)
        configuration = await client.guest_configuration(node, vmid, kind=kind)
        node_tasks = await client.node_tasks(node)
        guest_tasks = await client.guest_tasks(node, vmid, kind=kind)
        node_status = await client.node_status(node)
        datastores = await client.node_storage(node)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    lock = _lock(guest, node_tasks)
    disks = _disks(configuration)
    passthrough = _passthrough(configuration)
    reachable = {store.name for store in datastores if store.is_available}
    missing = sorted({name for name in disks.values() if name and name not in reachable})
    resources = _resources(node_status, guest)
    failures = _failures(guest_tasks, node_tasks, vmid)

    causes = _causes(
        status_quorate=status.quorate or not status.is_clustered,
        lock=lock,
        missing=missing,
        passthrough=passthrough,
        resources=resources,
        failures=failures,
    )
    value: dict[str, Any] = {
        "node": node,
        "guest": vmid,
        "kind": kind,
        "status": guest.status,
        "quorate": status.quorate or not status.is_clustered,
        "lock": lock,
        "disks": [{"key": key, "datastore": store} for key, store in sorted(disks.items())],
        "datastores_unreachable": missing,
        "passthrough_devices": passthrough,
        "node_resources": resources,
        "recent_failures": failures,
        "candidate_causes": causes,
        "most_likely_cause": causes[0] if causes else "nothing found that would stop it starting",
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=f"{kind}/{vmid} on {node}: {value['most_likely_cause']}",
        reference=f"proxmox:guest:{node}/{kind}/{vmid}",
        evidence_type=EvidenceType.ANALYSIS,
    )


def _lock(guest: GuestStatus, tasks: Sequence[TaskRecord]) -> dict[str, Any]:
    """Return the lock and whether anything is still holding it.

    The whole distinction is here: a lock whose task is running must not be
    cleared, and a lock whose task is gone is the thing to clear. The guest
    record carries the lock and never the task.
    """
    if not guest.lock:
        return {
            "held": False,
            "kind": "",
            "orphaned": False,
            "task": "",
            "task_age_seconds": 0,
            "verdict": "no lock is held",
        }

    now = int(datetime.now(UTC).timestamp())
    for task in tasks:
        if task.vmid != guest.vmid:
            continue
        if task.finished:
            continue
        return {
            "held": True,
            "kind": guest.lock,
            "orphaned": False,
            "task": task.upid,
            "task_type": task.task_type,
            "task_age_seconds": max(now - task.started_at, 0),
            "verdict": (
                f"the {task.task_type} task holding this lock is still running (started "
                f"{seconds_as_phrase(max(now - task.started_at, 0))} ago). Clearing the lock "
                f"now would corrupt what that task is doing."
            ),
        }

    latest = next((task for task in tasks if task.vmid == guest.vmid), None)
    age = max(now - latest.started_at, 0) if latest is not None else 0
    return {
        "held": True,
        "kind": guest.lock,
        "orphaned": True,
        "task": latest.upid if latest is not None else "",
        "task_type": latest.task_type if latest is not None else "",
        "task_age_seconds": age,
        "verdict": (
            f"the lock is {guest.lock!r} and no task for this guest is still running. The last "
            f"one was {latest.task_type if latest is not None else 'not found'}, "
            f"{seconds_as_phrase(age)} ago, and it "
            f"{'failed' if latest is not None and not latest.succeeded else 'ended'} — so this "
            f"lock is orphaned"
        ),
    }


def _disks(configuration: Mapping[str, Any]) -> dict[str, str]:
    """Return which datastore each configured disk is on, keyed by its config key."""
    found: dict[str, str] = {}
    for key, raw in configuration.items():
        name = str(key)
        if not any(name.startswith(prefix) for prefix in DISK_KEYS):
            continue
        value = str(raw)
        if ":" not in value:
            continue
        found[name] = value.split(":", 1)[0]
    return found


def _passthrough(configuration: Mapping[str, Any]) -> list[str]:
    """Return the configuration keys naming hardware this node alone has."""
    return sorted(
        str(key)
        for key in configuration
        if any(str(key).startswith(prefix) for prefix in PASSTHROUGH_KEYS)
    )


def _resources(node_status: Any, guest: GuestStatus) -> dict[str, Any]:
    """Return whether the node has room for what the guest is configured to use."""
    if not node_status.available:
        return {
            "known": False,
            "memory_available_for_guest": True,
            "reason": node_status.unavailable_reason,
        }
    status: NodeStatus = node_status.require()
    free = status.memory_total_bytes - status.memory_used_bytes
    return {
        "known": True,
        "node_memory_total_bytes": status.memory_total_bytes,
        "node_memory_free_bytes": free,
        "guest_memory_bytes": guest.memory_bytes,
        "memory_available_for_guest": free >= guest.memory_bytes,
        "node_memory_ratio": round(status.memory_ratio, 4),
        "node_swap_ratio": round(status.swap_ratio, 4),
    }


def _failures(
    guest_tasks: Sequence[TaskRecord], node_tasks: Sequence[TaskRecord], vmid: int
) -> list[dict[str, Any]]:
    """Return the guest's recent failed tasks with the vendor's own error text."""
    seen: dict[str, TaskRecord] = {}
    for task in list(guest_tasks) + [task for task in node_tasks if task.vmid == vmid]:
        if task.succeeded or not task.finished:
            continue
        seen.setdefault(task.upid, task)
    ordered = sorted(seen.values(), key=lambda task: task.started_at, reverse=True)
    return [
        {
            "upid": task.upid,
            "type": task.task_type,
            "started_at": task.started_at,
            "error": task.exit_status or task.status,
        }
        for task in ordered[:MAX_REPORTED_ITEMS]
    ]


def _causes(
    *,
    status_quorate: bool,
    lock: dict[str, Any],
    missing: list[str],
    passthrough: list[str],
    resources: dict[str, Any],
    failures: list[dict[str, Any]],
) -> list[str]:
    """Return the causes, most invalidating first.

    Order matters more than completeness. Without quorum nothing starts anywhere,
    so a lock or a full datastore found underneath it is a true finding and the
    wrong thing to act on first.
    """
    causes: list[str] = []
    if not status_quorate:
        causes.append(
            "the cluster has no quorum, so /etc/pve is read-only and no guest can be started "
            "anywhere — every finding below this one is downstream of it"
        )
    if lock["held"]:
        causes.append(lock["verdict"])
    if missing:
        causes.append(
            f"this guest has a disk on {', '.join(missing)}, which this node cannot currently "
            f"reach — a datastore reporting unknown is a failed mount rather than an empty one"
        )
    if passthrough:
        causes.append(
            f"this guest declares passthrough device(s) {', '.join(passthrough)}, which exist "
            f"on one node's hardware and nowhere else"
        )
    if resources.get("known") and not resources["memory_available_for_guest"]:
        causes.append(
            f"the node has {resources['node_memory_free_bytes']} bytes free and the guest is "
            f"configured for {resources['guest_memory_bytes']}, so there is not enough memory "
            f"for it here"
        )
    if failures:
        causes.append(
            f"its last failed task was {failures[0]['type']} and Proxmox said: "
            f"{failures[0]['error']}"
        )
    return causes


__all__ = ["DISK_KEYS", "PASSTHROUGH_KEYS", "TOOL_NAME", "proxmox_guest_start_diagnosis"]
