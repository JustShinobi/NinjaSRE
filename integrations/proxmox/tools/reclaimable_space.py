"""What could be freed, and — for every single entry — what it is protecting.

This is the most dangerous tool in the integration, because its output is a list
of things that could be deleted and the most reclaimable item is very often the
only recent recovery point. A report that ranks by size and stops there is a
report that recommends deleting exactly the wrong thing, in a font that makes it
look like advice.

So ``protects`` is a required field of every entry rather than a column that is
sometimes filled in. A snapshot protects the guest's state at a moment; a backup
is protected by a retention rule, or by nothing at all when the rule was never
set; an orphaned volume protects nothing and says so. There is no way to produce
an entry here without one, which is the whole point: the dangerous suggestion
cannot be made without its own warning attached.

The result is bounded by ranking rather than truncation — what each item would
return first, then how old it is — and it says it was bounded and by what. A
cluster with a thousand snapshots must not put a thousand entries into a small
model's context, and cutting an unranked list at twenty produces twenty
arbitrary snapshots instead of the twenty that would free the space.

Source of truth: each datastore's contents for backups and volumes, each guest's
snapshot list, the cluster resource list, and the backup job definitions for the
retention rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
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
    report,
    seconds_as_phrase,
)
from integrations.proxmox.models import BackupJob
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_reclaimable_space"

#: How many guests are opened for their snapshot lists. Snapshots are a per-guest
#: read and a node with fifty guests is fifty calls, which is a call budget an
#: investigation does not have. Exceeding it is reported rather than hidden.
MAX_GUESTS_EXAMINED = MAX_REPORTED_ITEMS

_USE_CASES = (
    "finding what could be freed on a node that is running out of space, with what each item "
    "is protecting",
    "checking whether the largest reclaimable item is the only recent recovery point",
    "seeing which backups are kept by a retention rule and which are kept by nothing",
)

_ANTI_EXAMPLES = (
    "deleting a snapshot, a backup or a volume — nothing here writes, and this is the tool "
    "whose output most resembles a delete list",
    "how full a datastore is, which proxmox_storage_pressure reads",
    "whether a guest is protected at all, which proxmox_backup_coverage answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox reclaimable space",
    description=(
        "Return what could be freed on a Proxmox node — snapshots, backups and orphaned "
        "volumes — with, for every entry, how much it would return and what it is protecting. "
        "No entry is produced without its protection statement, because the most reclaimable "
        "item is very often the only recent recovery point. Bounded by ranking rather than "
        "truncation, and it says what it ranked by."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "storage", "snapshot", "backup", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_reclaimable_space(node: str) -> CapabilityResult:
    """Return what could be freed on ``node``, each entry saying what it protects."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        resources = await client.cluster_resources()
        jobs = await client.backup_jobs()
        guests = [
            row
            for row in resources
            if row.get("type") in {"lxc", "qemu"} and str(row.get("node", "")) == node
        ]
        live = {
            int(row.get("vmid", 0) or 0) for row in resources if row.get("type") in {"lxc", "qemu"}
        }

        items: list[dict[str, Any]] = []
        for store in await client.node_storage(node):
            if not store.is_available:
                holes.append(
                    Undetermined(
                        question=f"what could be reclaimed from the {store.name} datastore",
                        reason=(
                            f"{node} reports it as {store.status!r} rather than available, so "
                            f"its contents could not be listed at all"
                        ),
                        published_by=f"the {store.name} mount on {node}",
                    )
                )
                continue
            for row in await client.datastore_contents(node, store.name):
                items.extend(_from_content(node, store.name, row, jobs=jobs, live=live))

        examined = guests[:MAX_GUESTS_EXAMINED]
        if len(guests) > len(examined):
            holes.append(
                Undetermined(
                    question=f"the snapshots of the {len(guests) - len(examined)} further "
                    f"guest(s) on {node}",
                    reason=(
                        f"snapshots are a per-guest read and this stops at "
                        f"{MAX_GUESTS_EXAMINED} guests, because a node with fifty of them is "
                        f"fifty calls an investigation cannot spend"
                    ),
                    published_by="each guest's own snapshot list",
                )
            )
        for row in examined:
            try:
                items.extend(await _snapshots(client, node, row))
            except IntegrationError as error:
                # A guest whose snapshot list cannot be read is a hole in the
                # total, not a failed tool — and it is the hole that matters,
                # because an unlisted snapshot is space nobody knows about.
                holes.append(
                    Undetermined(
                        question=f"the snapshots of guest {row.get('vmid')} on {node}",
                        reason=str(error),
                        published_by="that guest's own snapshot list",
                    )
                )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    kept, bound = bounded(
        items,
        ranked_by="what each item would return, then how old it is",
        key=lambda entry: (entry["reclaims_bytes"], entry["age_seconds"]),
    )
    value: dict[str, Any] = {
        "node": node,
        "items": list(kept),
        "reclaimable_bytes_known": sum(
            entry["reclaims_bytes"] for entry in items if entry["reclaims_bytes_known"]
        ),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(node, items, value),
        reference=f"proxmox:reclaimable:{node}",
        evidence_type=EvidenceType.CONFIGURATION,
        undetermined=holes,
        bounds=(("items", bound),),
    )


def _from_content(
    node: str,
    datastore: str,
    row: Mapping[str, Any],
    *,
    jobs: tuple[BackupJob, ...],
    live: set[int],
) -> list[dict[str, Any]]:
    """Return the reclaimable entry a datastore content row describes, if any."""
    volid = str(row.get("volid", ""))
    if not volid:
        return []
    vmid = int(row.get("vmid", 0) or 0)
    size = int(row.get("size", 0) or 0)
    created = int(row.get("ctime", 0) or 0)
    backup = str(row.get("content", "")) == "backup" or "/backup/" in volid

    if backup:
        return [
            _entry(
                kind="backup",
                reference=volid,
                node=node,
                datastore=datastore,
                vmid=vmid,
                reclaims=size,
                known=bool(size),
                created=created,
                protects=_backup_protection(vmid, jobs),
            )
        ]
    if vmid and vmid not in live:
        return [
            _entry(
                kind="orphaned-volume",
                reference=volid,
                node=node,
                datastore=datastore,
                vmid=vmid,
                reclaims=size,
                known=bool(size),
                created=created,
                protects=(
                    f"nothing: guest {vmid} is not in the cluster's resource list, so this is "
                    f"the disk of a guest that no longer exists"
                ),
            )
        ]
    return []


async def _snapshots(
    client: ProxmoxClient, node: str, row: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return one guest's snapshots as reclaimable entries, newest one flagged."""
    vmid = int(row.get("vmid", 0) or 0)
    kind = str(row.get("type", ""))
    name = str(row.get("name", "")) or f"{kind}/{vmid}"
    found = [
        snapshot
        for snapshot in await client.guest_snapshots(node, vmid, kind=kind)
        # ``current`` is not a snapshot. It is Proxmox's name for the running
        # state, and offering it as reclaimable would offer the guest itself.
        if str(snapshot.get("name", "")) != "current"
    ]
    if not found:
        return []

    newest = max(int(snapshot.get("snaptime", 0) or 0) for snapshot in found)
    entries: list[dict[str, Any]] = []
    for snapshot in found:
        taken = int(snapshot.get("snaptime", 0) or 0)
        sole = len(found) == 1
        protects = (
            f"the state of {name} (guest {vmid}) as it was at that moment"
            if not (sole or taken == newest)
            else (
                f"the state of {name} (guest {vmid}) as it was at that moment, and it is the "
                f"most recent snapshot of that guest — deleting it removes the only in-place "
                f"recovery point it has"
            )
        )
        entries.append(
            _entry(
                kind="snapshot",
                reference=f"{kind}/{vmid}@{snapshot.get('name', '')}",
                node=node,
                datastore="",
                vmid=vmid,
                reclaims=0,
                known=False,
                created=taken,
                protects=protects,
            )
        )
    return entries


def _entry(
    *,
    kind: str,
    reference: str,
    node: str,
    datastore: str,
    vmid: int,
    reclaims: int,
    known: bool,
    created: int,
    protects: str,
) -> dict[str, Any]:
    """Return one reclaimable item. There is no path here without ``protects``."""
    now = int(datetime.now(UTC).timestamp())
    age = max(now - created, 0) if created else 0
    return {
        "kind": kind,
        "reference": reference,
        "node": node,
        "datastore": datastore,
        "guest": vmid,
        "reclaims_bytes": reclaims,
        "reclaims_bytes_known": known,
        "created_at": created,
        "age_seconds": age,
        "age": seconds_as_phrase(age) if age else "unknown",
        "protects": protects,
    }


def _backup_protection(vmid: int, jobs: tuple[BackupJob, ...]) -> str:
    """Return what keeps a backup, which is a retention rule or nothing at all."""
    covering = [job for job in jobs if job.enabled and (job.covers_everything or vmid in job.vmids)]
    if not covering:
        return (
            f"a restore of guest {vmid}; no enabled backup job covers that guest, so nothing "
            f"will replace this copy and no retention rule is pruning it either"
        )
    rules = ", ".join(job.retention or "no retention rule set" for job in covering)
    names = ", ".join(job.job_id for job in covering)
    return (
        f"a restore of guest {vmid}; kept by job {names} whose retention is {rules} — deleting "
        f"it moves the oldest restorable point forward"
    )


def _summary(node: str, items: list[dict[str, Any]], value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not items:
        return f"{node}: nothing on this node is reclaimable without losing something in use"
    kinds: dict[str, int] = {}
    for entry in items:
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    breakdown = ", ".join(f"{count} {kind}(s)" for kind, count in sorted(kinds.items()))
    return (
        f"{node}: {breakdown} could be freed, returning at least "
        f"{value['reclaimable_bytes_known']} bytes — every entry carries what it is protecting, "
        f"and the largest is frequently the only recent recovery point"
    )


__all__ = ["MAX_GUESTS_EXAMINED", "TOOL_NAME", "proxmox_reclaimable_space"]
