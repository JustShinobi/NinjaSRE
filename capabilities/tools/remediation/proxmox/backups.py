"""Retrying a backup, and resyncing a replica, without breaking the next one.

Both actions here add a recovery point rather than removing one, which is why
they sit in the middle of the risk table. Both are also the ordinary way an
operator makes things worse on a small cluster, and the two preconditions below
are the reasons why.

**A retry must not collide with the schedule.** Two vzdump runs against one guest
contend for the same lock and the same datastore, and the scheduled one is the
one somebody depends on. A retry that starts an hour before the nightly job turns
one failed backup into two.

**A resync must be rate-limited, and it says what the limit is for.** Corosync
runs over the same link a storage sync will saturate. A cluster that loses its
membership layer to a replication job has traded a lagging replica for an
unquorate cluster, which is a strictly worse position — so the limit is a
parameter of the action rather than a setting somebody may not have.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from capabilities.tools.remediation import _base
from capabilities.tools.remediation.proxmox import signals
from capabilities.tools.remediation.proxmox.components import DeclaredPlanner, components_for
from capabilities.tools.remediation.proxmox.declaration import (
    ProxmoxRemediation,
    RollbackDeclaration,
    WriteCategory,
)
from capabilities.tools.remediation.proxmox.preconditions import Precondition
from capabilities.tools.remediation.proxmox.risk import class_of
from config.constants.hypervisor import (
    BACKUP_SETTLE_SECONDS,
    DEFAULT_REPLICATION_RATE_LIMIT_MBPS,
    REPLICATION_SETTLE_SECONDS,
)
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations.proxmox.privileges import RequiredPrivilege
from integrations.proxmox.schema import INTEGRATION
from platform.remediation.components import RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.models import RemediationAction, StateSnapshot

BACKUP_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="VM.Backup",
        path="/vms",
        grants="take a backup of a guest outside its schedule",
    ),
    RequiredPrivilege(
        privilege="Datastore.AllocateSpace",
        path="/storage",
        grants="write the backup it takes onto a datastore",
    ),
)

#: Replication is a node-level operation in Proxmox rather than a guest-level
#: one, and it is gated accordingly. Declared as the privilege that certainly
#: permits it, for the reason the high-availability one is: over-asking surfaces
#: as "your token needs more", where under-asking reports a token as sufficient
#: for a job it cannot do.
REPLICATION_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="Sys.Console",
        path="/",
        grants="run a storage replication job outside its schedule",
    ),
)


def _backed_up(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the intent of a retry: the guest's most recent backup succeeded."""
    del action, before
    return {"last_backup_succeeded": True}


def _replicated(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the intent of a resync: the job is no longer failing."""
    del action, before
    return {"failing": False}


RETRY_BACKUP = ProxmoxRemediation(
    capability="proxmox_retry_backup",
    category=WriteCategory.BACKUP,
    endpoint="/nodes/{node}/vzdump",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
        Precondition.NO_SCHEDULED_BACKUP_COLLISION,
    ),
    rollback=RollbackDeclaration(
        summary=(
            "A backup of {target} that ran cannot be un-run; it consumed space and time "
            "({restored})."
        ),
        steps=(
            "Confirm the task finished and what it wrote.",
            "If the copy should not have been taken, remove it deliberately through review "
            "rather than as part of undoing this.",
        ),
        reversible=False,
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(name=signals.BACKUP_AGE_HOURS, direction=SignalDirection.DOWN),
        ),
        settle_seconds=BACKUP_SETTLE_SECONDS,
    ),
    privileges=BACKUP_PRIVILEGES,
    fields=("last_backup_succeeded", "last_backup_at"),
    identity_fields=("last_backup_at",),
    intent_of=_backed_up,
    writes_configuration=True,
    operation="vzdump <vmid> --storage <storage> --mode snapshot",
    arguments=("node", "vmid", "kind", "storage"),
)

RESYNC_REPLICATION = ProxmoxRemediation(
    capability="proxmox_resync_replication",
    category=WriteCategory.REPLICATION,
    endpoint="/nodes/{node}/replication/{job}/schedule_now",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.NODE_NOT_AMBIGUOUSLY_DEAD,
    ),
    rollback=RollbackDeclaration(
        summary=(
            "A replication run for {target} cannot be un-run: the target now holds the "
            "source's state ({restored})."
        ),
        steps=(
            "Confirm the job finished and how long it held the link.",
            "If the link suffered, lower the rate limit before the next run rather than "
            "trying to reverse this one.",
        ),
        reversible=False,
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(
                name=signals.REPLICATION_LAG_SECONDS,
                direction=SignalDirection.DOWN,
            ),
        ),
        settle_seconds=REPLICATION_SETTLE_SECONDS,
    ),
    privileges=REPLICATION_PRIVILEGES,
    fields=("failing", "last_sync", "target"),
    identity_fields=("target",),
    intent_of=_replicated,
    writes_configuration=True,
    assumes_node_is_dead=True,
    operation="pvesr run --id <job> --verbose",
    arguments=("node", "job_id", "rate_limit_mbps"),
)

DECLARED: Final[tuple[ProxmoxRemediation, ...]] = (RETRY_BACKUP, RESYNC_REPLICATION)

COMPONENTS: Final[tuple[RemediationComponents, ...]] = (
    components_for(RETRY_BACKUP),
    components_for(RESYNC_REPLICATION),
)


@tool(
    name=RETRY_BACKUP.capability,
    display_name="Retry a Proxmox guest backup",
    description=(
        "Run one Proxmox guest's backup now, outside its schedule. Refuses when a scheduled "
        "run is close enough to collide with it, because two vzdump runs against one guest "
        "contend for the same lock and the same datastore."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    risk_class=class_of(RETRY_BACKUP.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest and its datastore carry the I/O for as long as it runs, and the copy it "
        "writes consumes space that a scheduled run may be counting on."
    ),
    rollback_planner=DeclaredPlanner(RETRY_BACKUP),
    tags=("proxmox", "remediation", "backup"),
    use_cases=(
        "retake a backup that failed for a reason since fixed",
        "take a copy before a change, when the last scheduled run is too old to rely on",
    ),
    anti_examples=(
        "retrying into the hour before a scheduled run, which this refuses",
        "retrying a backup whose failure is a full datastore",
    ),
)
def proxmox_retry_backup(node: str, vmid: int, kind: str, storage: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        RETRY_BACKUP.capability,
        detail=f"backup retry for {kind}/{vmid} on {node} onto {storage}",
    )


@tool(
    name=RESYNC_REPLICATION.capability,
    display_name="Resync a Proxmox replication job",
    description=(
        "Run one Proxmox storage replication job now, under an explicit rate limit. The "
        "limit is a parameter rather than a setting because corosync shares the link a "
        "resync saturates, and a cluster that loses its membership layer to a storage sync "
        "has traded a lagging replica for an unquorate cluster."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    risk_class=class_of(RESYNC_REPLICATION.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The run overwrites the target with the source's state and holds the link between "
        "the nodes for as long as it takes, which is the link corosync also runs over."
    ),
    rollback_planner=DeclaredPlanner(RESYNC_REPLICATION),
    tags=("proxmox", "remediation", "replication"),
    use_cases=(
        "catch up a replication job that has fallen behind its schedule",
        "re-run a job that failed while the link was down and has since returned",
    ),
    anti_examples=(
        "resyncing at full rate over the link corosync uses",
        "resyncing towards a node that is not answering",
    ),
)
def proxmox_resync_replication(
    node: str,
    job_id: str,
    rate_limit_mbps: int = DEFAULT_REPLICATION_RATE_LIMIT_MBPS,
) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        RESYNC_REPLICATION.capability,
        detail=f"resync of {job_id} on {node} at {rate_limit_mbps} MB/s",
    )


__all__ = [
    "BACKUP_PRIVILEGES",
    "COMPONENTS",
    "DECLARED",
    "REPLICATION_PRIVILEGES",
    "RESYNC_REPLICATION",
    "RETRY_BACKUP",
    "proxmox_resync_replication",
    "proxmox_retry_backup",
]
