"""How much work a node loss would cost, expressed as time rather than as an outcome.

A replication job that reports success and last ran a week ago reports success.
The reading that matters is the week: if the source node were lost now, the
target holds the guest as it was seven days ago and everything since is gone.
That is the recovery-point exposure, and it is what a job's status field never
says.

The other half of this tool is the case where there is nothing to iterate over.
**No replication jobs at all** is not an empty list — with guests on node-local
storage it means a node loss makes its guests unrecoverable inside the cluster,
which is the single most consequential fact about the reference cluster's data
posture and is invisible to anything that walks the jobs that exist. So the
absence is computed and reported as a finding, together with the guests it is a
finding about.

On a single-node installation the same absence means nothing: there is nowhere to
replicate to and nothing is wrong. That distinction is made rather than left to
the reader.

Source of truth: each node's ``/replication``, the cluster resource list, the
cluster's datastore declarations, and each guest's configuration for the disks it
actually sits on.
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
    MAX_REPORTED_ITEMS,
    Undetermined,
    bounded,
    observed_now,
    report,
    seconds_as_phrase,
)
from integrations.proxmox.models import ReplicationJob
from integrations.proxmox.schema import INTEGRATION
from integrations.proxmox.tools.guest_start_diagnosis import DISK_KEYS

TOOL_NAME = "proxmox_replication_lag"

#: Past this, a replication job's last success is old enough that the exposure
#: matters more than the outcome. A day of lost writes is a different incident
#: from an hour of them.
STALE_REPLICATION_SECONDS = 86_400

_USE_CASES = (
    "finding out how much work a node loss would cost right now, in time",
    "seeing that a cluster has no replication at all while its guests sit on local disks",
    "checking a replication job that reports success and has not actually run for days",
)

_ANTI_EXAMPLES = (
    "creating or running a replication job — nothing here writes",
    "whether a backup exists, which proxmox_backup_coverage answers",
    "whether a guest could migrate, which proxmox_migration_feasibility answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox replication lag",
    description=(
        "Return each Proxmox replication job's last success and the recovery-point exposure "
        "it leaves — how much work would be lost if the source node were lost now, stated in "
        "time. Reports the absence of any replication as a finding when guests sit on "
        "node-local storage, because a node loss then makes them unrecoverable inside the "
        "cluster and nothing that iterates over existing jobs can see it."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "replication", "recovery", "backup", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_replication_lag() -> CapabilityResult:
    """Return per-job exposure, and the absence of replication as its own finding."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        status = await client.cluster_status()
        resources = await client.cluster_resources()
        declared = {
            str(row.get("storage", "")): row for row in await client.storage_configuration()
        }
        nodes = [member.name for member in status.members]
        jobs = [job for node in nodes for job in await client.replication_jobs(node)]

        guests = [row for row in resources if row.get("type") in {"lxc", "qemu"}]
        examined = guests[:MAX_REPORTED_ITEMS]
        if len(guests) > len(examined):
            holes.append(
                Undetermined(
                    question=f"which datastores the remaining {len(guests) - len(examined)} "
                    f"guest(s) sit on",
                    reason=(
                        f"a guest's disks are a per-guest read and this stops at "
                        f"{MAX_REPORTED_ITEMS} guests, so the node-local count below is a "
                        f"floor rather than a total"
                    ),
                    published_by="each guest's own configuration",
                )
            )
        local: list[dict[str, Any]] = []
        for row in examined:
            vmid = int(row.get("vmid", 0) or 0)
            node = str(row.get("node", ""))
            kind = str(row.get("type", ""))
            try:
                configuration = await client.guest_configuration(node, vmid, kind=kind)
            except IntegrationError as error:
                # One guest that cannot be read is a hole in the count, not a
                # failed tool. Reporting nothing because the sixth guest's node
                # is down would hide the five that are genuinely exposed.
                holes.append(
                    Undetermined(
                        question=f"which datastores {kind}/{vmid} on {node} sits on",
                        reason=str(error),
                        published_by=f"the {node} node itself",
                    )
                )
                continue
            stores = _node_local(configuration, declared)
            if stores:
                local.append({"guest": vmid, "node": node, "datastores": stores})
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    now = int(observed_now().timestamp())
    replicated = {job.guest for job in jobs}
    unreplicated = [entry for entry in local if entry["guest"] not in replicated]
    matters = len(status.members) > 1 and status.is_clustered

    reported, bound = bounded(
        (_job(job, now=now) for job in jobs),
        ranked_by="the recovery-point exposure each job leaves",
        key=lambda entry: entry["recovery_point_exposure_seconds"],
    )
    value: dict[str, Any] = {
        "cluster": status.name,
        "jobs": list(reported),
        "no_replication_configured": not jobs,
        "recoverable_elsewhere_matters": matters,
        "guests_on_node_local_storage": [entry["guest"] for entry in unreplicated],
        "guests_on_node_local_storage_detail": unreplicated,
        "worst_exposure_seconds": max(
            (entry["recovery_point_exposure_seconds"] for entry in reported), default=0
        ),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(value, matters=matters),
        reference=f"proxmox:replication:{status.name or 'standalone'}",
        undetermined=holes,
        bounds=(("jobs", bound),),
    )


def _node_local(configuration: Mapping[str, Any], declared: Mapping[str, Any]) -> list[str]:
    """Return the guest's datastores that live on one node and cannot follow it.

    Both shapes count: a datastore Proxmox marks unshared, and one the cluster
    restricts to a subset of nodes. Either way the guest is where its disk is.
    """
    found: set[str] = set()
    for key, raw in configuration.items():
        name = str(key)
        if not any(name.startswith(prefix) for prefix in DISK_KEYS):
            continue
        value = str(raw)
        if ":" not in value:
            continue
        store = value.split(":", 1)[0]
        row = declared.get(store)
        if row is None:
            continue
        shared = bool(int(row.get("shared", 0) or 0))
        restricted = bool(str(row.get("nodes", "") or "").strip())
        if not shared or restricted:
            found.add(store)
    return sorted(found)


def _job(job: ReplicationJob, *, now: int) -> dict[str, Any]:
    """Return one job read by exposure rather than by outcome."""
    exposure = max(now - job.last_sync, 0) if job.last_sync else 0
    return {
        "id": job.job_id,
        "guest": job.guest,
        "source": job.source,
        "target": job.target,
        "enabled": job.enabled,
        "last_sync": job.last_sync,
        "last_run_succeeded": not job.failing,
        "error": job.error,
        "duration_seconds": job.duration_seconds,
        "recovery_point_exposure_seconds": exposure,
        "recovery_point_exposure": seconds_as_phrase(exposure) if exposure else "never ran",
        "stale": exposure > STALE_REPLICATION_SECONDS,
        "meaning": (
            f"if {job.source or 'the source node'} were lost now, {job.target or 'the target'} "
            f"holds guest {job.guest} as it was {seconds_as_phrase(exposure)} ago and "
            f"everything written since would be gone"
        ),
    }


def _summary(value: dict[str, Any], *, matters: bool) -> str:
    """Return the one line a conclusion can be checked against."""
    if value["no_replication_configured"]:
        if not matters:
            return (
                "no replication is configured, and on a single-node installation there is "
                "nowhere to replicate to — this is not a gap"
            )
        exposed = value["guests_on_node_local_storage"]
        if not exposed:
            return (
                "no replication job exists on this cluster; no guest was found on node-local "
                "storage, so nothing was established as unrecoverable"
            )
        return (
            f"NO replication job exists on this cluster and {len(exposed)} guest(s) sit on "
            f"node-local storage: losing their node makes them unrecoverable inside the "
            f"cluster, whatever the backups say"
        )
    stale = [job["id"] for job in value["jobs"] if job["stale"]]
    if stale:
        return (
            f"job(s) {', '.join(stale)} last succeeded more than a day ago; the worst "
            f"recovery-point exposure on this cluster is "
            f"{seconds_as_phrase(value['worst_exposure_seconds'])} of lost writes"
        )
    return (
        f"{len(value['jobs'])} replication job(s); the worst recovery-point exposure is "
        f"{seconds_as_phrase(value['worst_exposure_seconds'])}"
    )


__all__ = ["STALE_REPLICATION_SECONDS", "TOOL_NAME", "proxmox_replication_lag"]
