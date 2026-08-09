"""Backups that ran and did not work, in the vendor's own words.

Proxmox says what went wrong in prose and the prose is the useful part. "job
errors" and "storage 'remote-backup' is not online" and "unable to open file for
reading" all end a backup and each names a different thing to look at. Rewriting
them into a category loses exactly the information a next step would come from,
so the exit status is carried verbatim.

The reading that a failure list on its own does not make is **a guest whose every
attempt failed**. A guest with a failure yesterday and a success the day before
has a backup; a guest with nothing but failures has never had one, and the two
are the same row in a list of failures. So the successes are read alongside and
the guests with none are named separately — that set is the one where a restore
is not an option at all.

Source of truth: each node's task history, filtered to ``vzdump``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import bounded, report, seconds_as_phrase
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_backup_failures"

_USE_CASES = (
    "reading why a backup failed, in the words Proxmox used rather than a category",
    "finding the guests whose every backup attempt has failed, which a failure list hides",
    "checking whether a backup window failed as a whole or one guest inside it did",
)

_ANTI_EXAMPLES = (
    "re-running a backup — nothing here writes",
    "which guests no job covers, which proxmox_backup_coverage answers",
    "whether a stored backup would restore, which the Backup Server's verification answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox backup failures",
    description=(
        "Return the Proxmox backup tasks that failed, each with the vendor's own error text, "
        "and — separately — the guests whose every attempt has failed. A guest that failed "
        "last night and succeeded the night before has a backup; a guest with nothing but "
        "failures has never had one, and both are one row in a list of failures."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "backup", "failure", "recovery", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_backup_failures() -> CapabilityResult:
    """Return every failed backup task with its error, and the guests with no success."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        resources = await client.cluster_resources()
        nodes = sorted({str(row.get("node", "")) for row in resources if row.get("type") == "node"})
        attempted: set[int] = set()
        succeeded: set[int] = set()
        failed: list[dict[str, Any]] = []
        now = int(datetime.now(UTC).timestamp())
        for node in nodes:
            for task in await client.backup_outcomes(node):
                if not task.vmid:
                    continue
                attempted.add(task.vmid)
                if task.succeeded:
                    succeeded.add(task.vmid)
                    continue
                if not task.finished:
                    continue
                failed.append(
                    {
                        "guest": task.vmid,
                        "node": node,
                        "upid": task.upid,
                        "started_at": task.started_at,
                        "age": seconds_as_phrase(max(now - task.started_at, 0)),
                        "duration_seconds": task.duration_seconds,
                        # Verbatim. The category a paraphrase would produce is
                        # the part that stops naming the next thing to look at.
                        "error": task.exit_status or task.status,
                        "user": task.user,
                    }
                )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    failures, bound = bounded(
        failed, ranked_by="how recently each attempt ran", key=lambda entry: entry["started_at"]
    )
    never = sorted(attempted - succeeded)
    value: dict[str, Any] = {
        "failures": list(failures),
        "guests_attempted": sorted(attempted),
        "guests_with_no_successful_backup": never,
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(failed, never),
        reference="proxmox:backup-failures",
        evidence_type=EvidenceType.EVENT,
        bounds=(("failures", bound),),
    )


def _summary(failed: list[dict[str, Any]], never: list[int]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not failed:
        return "no backup task on this cluster has failed in the history that is retained"
    parts = [f"{len(failed)} backup task(s) failed"]
    if never:
        parts.append(
            f"guest(s) {', '.join(str(vmid) for vmid in never)} have never had a successful "
            f"backup at all, so a restore is not available for them"
        )
    parts.append(f"the most recent said: {failed[0]['error']}")
    return "; ".join(parts)


__all__ = ["TOOL_NAME", "proxmox_backup_failures"]
