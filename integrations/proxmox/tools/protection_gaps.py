"""Which guests would survive losing the node they are on, and which would not.

Two mechanisms protect a Proxmox guest and both fail quietly.

**A backup job that exists and is switched off.** Every inventory of "is there a
backup job covering this guest" answers yes, because there is one — it is
disabled. On the reference cluster the job covering roughly fifty-five guests,
including the entire observability stack, is in exactly that state. This tool
answers the question that matters instead: is this guest covered by an *enabled*
job.

**Replication that was never configured.** With guests on node-local storage and
no replication, losing a node means its guests are unavailable until they are
restored from a backup — and if the backup job covering them is the disabled one,
there is nothing to restore from. Neither half is visible on its own; together
they are the difference between an inconvenience and a rebuild.

Source of truth: ``/cluster/backup`` for the job definitions, the cluster
resource list for the guests, and each node's ``/replication``.
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

TOOL_NAME = "proxmox_protection_gaps"

_USE_CASES = (
    "finding which guests are covered by no enabled backup job",
    "checking whether a node loss is recoverable inside the cluster at all",
    "seeing a backup job that exists and is switched off, which every coverage count misses",
)

_ANTI_EXAMPLES = (
    "restoring a guest, or running a backup — nothing here writes",
    "whether a backup that ran succeeded, which the task history answers",
    "how full the backup datastore is, which proxmox_storage_pressure reads",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox protection gaps",
    description=(
        "Return which Proxmox guests are covered by an enabled backup job, which are covered "
        "only by a disabled one, and whether any replication exists. A job that exists and is "
        "switched off satisfies every coverage count and protects nothing."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "backup", "replication", "resilience", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_protection_gaps() -> CapabilityResult:
    """Return the guests no enabled backup job covers, and whether anything replicates."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        jobs = await client.backup_jobs()
        resources = await client.cluster_resources()
        nodes = [str(row.get("node", "")) for row in resources if row.get("type") == "node"]
        replication = [job for node in nodes for job in await client.replication_jobs(node)]
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    guests = {
        int(row.get("vmid", 0) or 0): str(row.get("name", ""))
        or f"{row.get('type')}/{row.get('vmid')}"
        for row in resources
        if row.get("type") in {"lxc", "qemu"}
    }
    covered: set[int] = set()
    for job in jobs:
        if not job.enabled:
            continue
        covered |= set(guests) if job.covers_everything else set(job.vmids)

    uncovered = sorted(set(guests) - covered)
    value: dict[str, Any] = {
        "jobs": [
            {
                "id": job.job_id,
                "comment": job.comment,
                "enabled": job.enabled,
                "covers": job.covers,
                "schedule": job.schedule,
                "retention": job.retention,
            }
            for job in jobs
        ],
        "disabled_jobs": [job.job_id for job in jobs if not job.enabled],
        "guests_without_an_enabled_job": [
            {"vmid": vmid, "name": guests[vmid]} for vmid in uncovered
        ],
        "replication_jobs": len(replication),
    }
    return CapabilityResult.ok(
        TOOL_NAME,
        value=value,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CONFIGURATION,
                summary=_summary(len(guests), uncovered, value),
                reference="proxmox:protection",
            ),
        ),
    )


def _summary(total: int, uncovered: list[int], value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    parts = [f"{len(uncovered)} of {total} guest(s) are covered by no enabled backup job"]
    if value["disabled_jobs"]:
        parts.append(f"disabled job(s): {', '.join(value['disabled_jobs'])}")
    if not value["replication_jobs"]:
        parts.append("no replication job exists, so a node loss is not recoverable in-cluster")
    return "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_protection_gaps"]
