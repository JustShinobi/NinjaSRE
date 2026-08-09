"""One guest's recent operations, and what the vendor said when they failed.

The task history is where Proxmox keeps its own account of what was attempted
and what went wrong, in its own words. Those words matter: "storage
'externo-nfs-pve01' is not online" and "no such logical volume" both present as a
guest that will not start, and each names the thing to look at next. Paraphrasing
them loses exactly the part that was useful.

Two shapes are separated because they support different conclusions. A task that
**failed** carries an error and is evidence. A task that is **still running** is
not evidence of anything yet, and is the reason a lock is held — reading it as a
failure is how a live backup gets cancelled.

An empty history is a reading and is reported as one. A guest with no tasks has
not been touched through the API, which usually means whatever happened to it
happened on the node rather than through Proxmox — and that is a finding rather
than an absence of one.

Source of truth: the guest's own ``/status/tasks``, and its node's task list for
the entries recorded against it there.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import bounded, report, seconds_as_phrase
from integrations.proxmox.models import TaskRecord
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_guest_tasks"

_USE_CASES = (
    "reading the vendor's own error text from a guest's most recent failed operation",
    "finding out whether a task against a guest is still running before touching its lock",
    "establishing that a guest has no API task history, which means it was changed on the node",
)

_ANTI_EXAMPLES = (
    "cancelling or re-running a task — nothing here writes",
    "why the guest will not start, which proxmox_guest_start_diagnosis answers using this",
    "cluster-wide backup failures, which proxmox_backup_failures reads",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox guest task history",
    description=(
        "Return a Proxmox guest's recent tasks with the vendor's own error text, keeping "
        "failed tasks apart from ones that are still running. A running task is not evidence "
        "of a failure and is usually the reason a lock is held. An empty history is reported "
        "as a finding: the guest was changed on the node rather than through the API."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "guest", "task", "history", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_guest_tasks(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return guest ``vmid``'s recent tasks, failures and running work separated."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        own = await client.guest_tasks(node, vmid, kind=kind)
        on_node = [task for task in await client.node_tasks(node) if task.vmid == vmid]
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    merged: dict[str, TaskRecord] = {}
    for task in list(own) + on_node:
        merged.setdefault(task.upid, task)

    tasks, bound = bounded(
        (_task(task) for task in merged.values()),
        ranked_by="how recently each task started",
        key=lambda entry: entry["started_at"],
    )
    failures = [entry for entry in tasks if entry["failed"]]
    running = [entry for entry in tasks if not entry["finished"]]
    value: dict[str, Any] = {
        "node": node,
        "guest": vmid,
        "kind": kind,
        "tasks": list(tasks),
        "failures": failures,
        "running": running,
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, vmid, kind, tasks, failures, running),
        reference=f"proxmox:tasks:{node}/{kind}/{vmid}",
        evidence_type=EvidenceType.EVENT,
        bounds=(("tasks", bound),),
    )


def _task(task: TaskRecord) -> dict[str, Any]:
    """Return one task, with the vendor's error text kept verbatim."""
    return {
        "upid": task.upid,
        "type": task.task_type,
        "started_at": task.started_at,
        "duration_seconds": task.duration_seconds,
        "finished": task.finished,
        "failed": task.finished and not task.succeeded,
        "error": "" if task.succeeded else (task.exit_status or task.status),
        "user": task.user,
    }


def _summary(
    node: str,
    vmid: int,
    kind: str,
    tasks: Sequence[dict[str, Any]],
    failures: Sequence[dict[str, Any]],
    running: Sequence[dict[str, Any]],
) -> str:
    """Return the one line a conclusion can be checked against."""
    if not tasks:
        return (
            f"{kind}/{vmid} on {node} has no task history at all, so nothing has been done to "
            f"it through the Proxmox API — whatever changed was changed on the node itself"
        )
    parts = [f"{len(tasks)} recent task(s)"]
    if running:
        parts.append(
            f"{len(running)} still running, including {running[0]['type']} — that is why a lock "
            f"would be held, and it is not a failure"
        )
    if failures:
        parts.append(
            f"the most recent failure was {failures[0]['type']} "
            f"({seconds_as_phrase(failures[0]['duration_seconds'])}) and Proxmox said: "
            f"{failures[0]['error']}"
        )
    return f"{kind}/{vmid} on {node}: " + "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_guest_tasks"]
