"""Which guests are actually protected, counted the way that gives the true answer.

Three counts look like coverage and only one of them is.

**Job membership** answers yes for a guest named by a job that is switched off.
The reference cluster's whole-node job is exactly that, and every inventory that
counts membership reports its guests as protected. So coverage here is computed
against **enabled** jobs only, and a disabled job is reported as the specific
danger it is rather than as a job.

**Coverage without depth** reads the same for two retained copies and for
thirty. A guest whose job keeps the last two backups has two days of history if
it runs daily, and a corruption discovered on the third day is unrecoverable
from a guest that every dashboard calls protected. So the retention depth is
reported beside the coverage, and a job with no retention rule at all is reported
as depth *unknown* rather than as depth zero — nothing is pruning it and nothing
is bounding it either.

**A job that covers a guest** is not a backup of that guest. What proves a backup
exists is a *successful task* and a file with a size and a date, so those are
read too, and a guest whose every attempt failed is absent from the successes
rather than present with an old one.

Source of truth: ``/cluster/backup`` for the definitions, the cluster resource
list for the guests, each node's task history for the outcomes, and each
datastore's contents for the sizes.
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
    bounded,
    observed_now,
    report,
    seconds_as_phrase,
)
from integrations.proxmox.models import BackupJob, TaskRecord
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_backup_coverage"

_USE_CASES = (
    "finding which guests no enabled backup job covers, as opposed to which are named by one",
    "checking how many copies a job actually retains before trusting it as history",
    "reading each guest's last successful backup with its age and size, not its job membership",
)

_ANTI_EXAMPLES = (
    "running a backup or enabling a job — nothing here writes",
    "why a backup failed, which proxmox_backup_failures reads with the vendor's error",
    "whether a Backup Server snapshot was verified, which the Backup Server answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox backup coverage",
    description=(
        "Return which Proxmox guests an *enabled* backup job covers, each guest's last "
        "successful backup with its age and size, and the retention depth of every job. A job "
        "that exists and is switched off satisfies every coverage count and protects nothing; "
        "two retained copies and thirty read identically without the depth."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "backup", "retention", "recovery", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_backup_coverage() -> CapabilityResult:
    """Return per-guest coverage against enabled jobs, with depth and last success."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        jobs = await client.backup_jobs()
        resources = await client.cluster_resources()
        nodes = sorted({str(row.get("node", "")) for row in resources if row.get("type") == "node"})
        successes: dict[int, TaskRecord] = {}
        sizes: dict[int, dict[str, Any]] = {}
        for node in nodes:
            for vmid, task in (await client.last_successful_backup(node)).items():
                held = successes.get(vmid)
                if held is None or task.started_at > held.started_at:
                    successes[vmid] = task
            for store in await client.node_storage(node):
                if not store.is_available:
                    continue
                for row in await client.datastore_contents(node, store.name, content="backup"):
                    _record_size(sizes, row)
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

    now = int(observed_now().timestamp())
    last = [
        {
            "guest": vmid,
            "name": guests.get(vmid, str(vmid)),
            "finished_at": task.ended_at or task.started_at,
            "age_seconds": max(now - (task.ended_at or task.started_at), 0),
            "age": seconds_as_phrase(max(now - (task.ended_at or task.started_at), 0)),
            "size_bytes": sizes.get(vmid, {}).get("size", 0),
            "volid": sizes.get(vmid, {}).get("volid", ""),
        }
        for vmid, task in sorted(successes.items())
        if vmid in guests
    ]
    uncovered, bound = bounded(
        (
            {"guest": vmid, "name": guests[vmid], "has_any_backup": vmid in successes}
            for vmid in sorted(set(guests) - covered)
        ),
        ranked_by="guest id, since an uncovered guest has no size to rank by",
        key=lambda entry: -int(str(entry["guest"])),
    )

    value: dict[str, Any] = {
        "jobs": [_job(job) for job in jobs],
        "disabled_jobs": [job.job_id for job in jobs if not job.enabled],
        "guests": len(guests),
        "guests_covered_by_an_enabled_job": sorted(covered & set(guests)),
        "guests_without_an_enabled_job": list(uncovered),
        "last_successful": last,
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(value),
        reference="proxmox:backup-coverage",
        evidence_type=EvidenceType.CONFIGURATION,
        bounds=(("guests_without_an_enabled_job", bound),),
    )


def _record_size(sizes: dict[int, dict[str, Any]], row: Mapping[str, Any]) -> None:
    """Keep the newest backup file per guest, which is the one its age refers to."""
    vmid = int(row.get("vmid", 0) or 0)
    if not vmid:
        return
    created = int(row.get("ctime", 0) or 0)
    held = sizes.get(vmid)
    if held is None or created >= held["ctime"]:
        sizes[vmid] = {
            "ctime": created,
            "size": int(row.get("size", 0) or 0),
            "volid": str(row.get("volid", "")),
        }


def _job(job: BackupJob) -> dict[str, Any]:
    """Return one job with its depth, which coverage alone does not carry."""
    depth = retention_depth(job.retention)
    return {
        "id": job.job_id,
        "comment": job.comment,
        "enabled": job.enabled,
        "schedule": job.schedule,
        "storage": job.storage,
        "node": job.node,
        "covers_everything": job.covers_everything,
        "covers": job.covers,
        "guests": list(job.vmids),
        "retention": job.retention or "no retention rule is set, so nothing prunes this job",
        "retention_depth": depth,
    }


def retention_depth(rule: str) -> int | None:
    """Return how many copies a Proxmox retention rule keeps, or ``None`` if unset.

    ``None`` rather than zero, deliberately. A job with no rule keeps everything
    until the datastore fills, which is a different position from a job that
    keeps nothing — and reporting it as zero would rank it as the worst job on
    the cluster when it is merely the least bounded.
    """
    text = rule.strip()
    if not text:
        return None
    total = 0
    found = False
    for part in text.split(","):
        key, separator, value = part.partition("=")
        if not separator or not key.strip().startswith("keep-"):
            continue
        digits = value.strip()
        if digits.isdigit():
            total += int(digits)
            found = True
    return total if found else None


def _summary(value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    uncovered = value["guests_without_an_enabled_job"]
    parts = [f"{len(uncovered)} of {value['guests']} guest(s) are covered by no enabled job"]
    if value["disabled_jobs"]:
        parts.append(
            f"job(s) {', '.join(value['disabled_jobs'])} are disabled and name guests that "
            f"therefore have no coverage at all"
        )
    shallow = [
        job["id"]
        for job in value["jobs"]
        if job["enabled"] and job["retention_depth"] is not None and job["retention_depth"] <= 2
    ]
    if shallow:
        parts.append(
            f"job(s) {', '.join(shallow)} retain two copies or fewer, so a corruption noticed "
            f"late is not recoverable from them"
        )
    return "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_backup_coverage", "retention_depth"]
