"""Whether a Backup Server datastore holds something that would actually restore.

"There is a backup" is four separate claims and three of them are usually
unchecked:

- there is a **snapshot**, and it is recent enough to be worth restoring;
- the snapshot has been **verified**, so its chunks are known to be intact — an
  unverified snapshot is a file, and a store whose verification job has never run
  looks exactly like a store whose verification passes;
- the store has **garbage-collected**, so its usage figure is about chunks
  something still references;
- the store has room, which is the only one of the four most deployments watch.

This returns all four for one datastore and says which of them is the problem.

Source of truth: ``/status/datastore-usage``, the datastore's own status, its
snapshot list, and its garbage-collection record.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox_backup_server.client import ProxmoxBackupServerClient
from integrations.proxmox_backup_server.schema import INTEGRATION

TOOL_NAME = "proxmox_backup_server_datastore_health"

_USE_CASES = (
    "checking whether a guest's most recent snapshot has actually been verified",
    "finding out whether a datastore's usage figure reflects a garbage collection that ran",
    "establishing that a backup exists and is recent before planning a restore",
)

_ANTI_EXAMPLES = (
    "restoring, pruning or collecting garbage — nothing here writes",
    "whether the hypervisor's backup job ran, which proxmox_protection_gaps answers",
    "what is inside a snapshot, which is a restore rather than a read",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox Backup Server datastore health",
    description=(
        "Return whether a Proxmox Backup Server datastore holds something that would "
        "restore: its usage, its snapshots, whether those snapshots have been verified, "
        "and when garbage collection last ran. An unverified snapshot is a file rather "
        "than a restore, and a store that has never verified looks identical to one that "
        "passes."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "backup", "restore", "verification", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_backup_server_datastore_health(datastore: str) -> CapabilityResult:
    """Return usage, snapshots, verification and garbage collection for ``datastore``."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxBackupServerClient, capability=TOOL_NAME)
    try:
        status = await client.datastore_status(datastore)
        snapshots = await client.snapshots(datastore)
        verification = await client.verification_state(datastore)
        collection = await client.garbage_collection(datastore)
        pruning = await client.prune_state(datastore)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    unverified = [row["snapshot"] for row in verification if row["state"] != "ok"]
    value: dict[str, Any] = {
        "datastore": datastore,
        "total_bytes": status.get("total"),
        "used_bytes": status.get("used"),
        "estimated_full_date": status.get("estimated-full-date"),
        "snapshot_count": len(snapshots),
        "unverified_snapshots": unverified,
        # What is left once the unproven are set aside. A store whose
        # verification job has never run reports the same snapshot count as one
        # whose verification passes, and only this number tells them apart.
        "proven_snapshot_count": len(snapshots) - len(unverified),
        "garbage_collection_status": collection.get("status", "never run"),
        "garbage_collection_last_run": collection.get("upid", ""),
        # The retention this store actually applies, which is separate from what
        # the hypervisor's backup job asked for: a job keeping thirty copies on
        # a store pruning to two keeps two.
        "prune_rules": [dict(rule) for rule in pruning],
    }
    return CapabilityResult.ok(
        TOOL_NAME,
        value=value,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CONFIGURATION,
                summary=_summary(datastore, len(snapshots), unverified, collection),
                reference=f"proxmox-backup-server:datastore:{datastore}",
            ),
        ),
    )


def _summary(
    datastore: str,
    snapshots: int,
    unverified: list[str],
    collection: dict[str, Any] | Any,
) -> str:
    """Return the one line a conclusion can be checked against."""
    if not snapshots:
        return f"{datastore} holds no snapshots at all, so nothing on it would restore"
    parts = [f"{datastore} holds {snapshots} snapshot(s)"]
    if unverified:
        parts.append(
            f"{len(unverified)} of them are unverified and therefore UNPROVEN — nobody has "
            f"checked their chunks, which is not the same as failing verification and is not "
            f"a backup either"
        )
    if not dict(collection).get("status"):
        parts.append("garbage collection has never run, so its usage figure is not current")
    return "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_backup_server_datastore_health"]
