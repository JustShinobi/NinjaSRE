"""Making room, by deleting exactly what somebody named and nothing else.

"Delete the oldest snapshots until there is room" is one bad night away from
deleting the recovery point somebody needed. So reclamation takes an explicit
list of volume identifiers; choosing them is a proposal a person approves, and a
policy expression cannot be passed at all — ``items_of`` refuses anything that is
not a volume identifier, by shape, before the action is built.

Both capabilities here declare that they have **no rollback**. That is not an
omission: a deleted snapshot has no undo, and saying so sends the request down
the waiver path, where an operator has to accept the absence explicitly and the
acceptance is audited. Inventing a plan that could not run would be worse than
having none.

Neither of them may extend a pool. Growing an LVM-thin or ZFS pool consumes the
only spare capacity a node has, and spending it is a decision with a budget
attached — so it is proposed to a person and the prohibition is asserted over the
whole registry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from config.constants.hypervisor import MAX_RECLAIMED_ITEMS, STORAGE_SETTLE_SECONDS
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
from platform.remediation.errors import RemediationError
from platform.remediation.models import RemediationAction, StateSnapshot

STORAGE_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="Datastore.Allocate",
        path="/storage",
        grants="remove a volume from a datastore",
    ),
)

_FREED = VerificationDeclaration(
    signals=(
        VerificationSignal(name=signals.DATASTORE_USED_PERCENT, direction=SignalDirection.DOWN),
    ),
    settle_seconds=STORAGE_SETTLE_SECONDS,
)


class ReclamationPolicyRefused(RemediationError):
    """Something asked for a rule instead of a list of things to delete.

    The one refusal in this module that happens before an action exists at all.
    A policy is evaluated at execution against whatever the datastore holds then,
    which is how "the oldest three" becomes "the only three" on the night the
    backups have been failing.
    """

    def __init__(self, offered: str) -> None:
        super().__init__(
            f"{offered!r} is not a volume identifier, so it is a rule for choosing what to "
            f"delete rather than a thing to delete. Reclamation takes an explicit list — "
            f"``store:content/name`` — because a rule is evaluated against whatever the "
            f"datastore holds at execution, and nobody reviewed that."
        )
        self.offered = offered


def items_of(raw: Sequence[str]) -> tuple[str, ...]:
    """Return ``raw`` as volume identifiers, refusing anything that is a policy.

    Shape is the whole check: a Proxmox volume identifier is
    ``datastore:content/name`` and nothing an operator would type as a rule looks
    like one. Bounded as well as validated, because a list long enough to be
    unreadable is a policy again.

    Raises:
        ReclamationPolicyRefused: an entry is not a volume identifier.
        ValueError: nothing was named, or more was named than may be reviewed.
    """
    named = [str(entry).strip() for entry in raw if str(entry).strip()]
    if not named:
        raise ValueError(
            "A reclamation names the volumes it deletes. One that named none would be a "
            "reclamation whose scope is decided somewhere else."
        )
    if len(named) > MAX_RECLAIMED_ITEMS:
        raise ValueError(
            f"{len(named)} items is more than the {MAX_RECLAIMED_ITEMS} a single reclamation "
            f"may name. A list nobody can read through is a policy with extra steps."
        )
    for entry in named:
        head, separator, tail = entry.partition(":")
        if not separator or not head or not tail:
            raise ReclamationPolicyRefused(entry)
    return tuple(named)


def _emptied(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the intent of a deletion: none of the named items is still there."""
    del action, before
    return {"items": []}


def _unowned(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the intent of an orphan removal: the volume is gone and owned by nobody."""
    del action, before
    return {"volumes": [], "owners": {}}


RECLAIM = ProxmoxRemediation(
    capability="proxmox_reclaim_storage",
    category=WriteCategory.STORAGE,
    endpoint="/nodes/{node}/storage/{datastore}/content/{volume}",
    method="DELETE",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE,
        Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM,
    ),
    rollback=RollbackDeclaration.none(
        "a deleted snapshot or backup has no undo. What it protected is recoverable only "
        "from a copy this system did not write to, which is why an operator has to accept "
        "the absence of a plan explicitly before this runs"
    ),
    verification=_FREED,
    privileges=STORAGE_PRIVILEGES,
    fields=("items", "used_bytes"),
    identity_fields=("items",),
    intent_of=_emptied,
    writes_configuration=False,
    operation="pvesm free <volume>",
    arguments=("node", "datastore", "items"),
)

REMOVE_ORPHAN = ProxmoxRemediation(
    capability="proxmox_remove_orphaned_volume",
    category=WriteCategory.STORAGE,
    endpoint="/nodes/{node}/storage/{datastore}/content/{volume}",
    method="DELETE",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.VOLUME_BELONGS_TO_NO_GUEST,
        Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE,
    ),
    rollback=RollbackDeclaration.none(
        "the volume and everything in it are gone. A disk belongs to nobody only as far as "
        "anybody checked, so the absence of a plan is accepted explicitly and audited"
    ),
    verification=_FREED,
    privileges=STORAGE_PRIVILEGES,
    fields=("volumes", "owners"),
    identity_fields=("volumes", "owners"),
    intent_of=_unowned,
    writes_configuration=False,
    operation="pvesm free <volume>",
    arguments=("node", "datastore", "volume"),
)

DECLARED: Final[tuple[ProxmoxRemediation, ...]] = (RECLAIM, REMOVE_ORPHAN)

COMPONENTS: Final[tuple[RemediationComponents, ...]] = (
    components_for(RECLAIM),
    components_for(REMOVE_ORPHAN),
)


@tool(
    name=RECLAIM.capability,
    display_name="Reclaim named Proxmox datastore items",
    description=(
        "Delete an explicit list of volumes from a Proxmox datastore. Takes the identifiers "
        "themselves and never a rule such as 'oldest first', because a rule is evaluated "
        "against whatever the datastore holds at execution and nobody reviewed that. Any "
        "item that is a recovery point — a snapshot, a backup, the last replication base — "
        "is the highest risk class regardless of its size."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.DESTRUCTIVE,
    risk_class=class_of(RECLAIM.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "Deletion is permanent and there is no rollback. If one of these items was the only "
        "recent recovery point for a guest, this removes the way back."
    ),
    rollback_planner=DeclaredPlanner(RECLAIM),
    tags=("proxmox", "remediation", "storage", "reclamation"),
    use_cases=(
        "free space on a datastore by removing items an operator has reviewed and named",
        "remove backups of a guest that no longer exists, once somebody has confirmed it",
    ),
    anti_examples=(
        "deleting by a rule such as 'the oldest three', which this refuses",
        "deleting a backup in order to make room for a backup",
    ),
)
def proxmox_reclaim_storage(node: str, datastore: str, items: list[str]) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate.

    The refusal comes before the item list is looked at, deliberately: a
    directly-invoked remediation capability is refused for being directly
    invoked, and reporting a malformed argument instead would tell the caller it
    was one correction away from performing the action. ``items_of`` runs where
    the deletion actually happens.
    """
    return _base.refuse(
        RECLAIM.capability,
        detail=f"reclamation of {len(items)} item(s) from {datastore} on {node}",
    )


@tool(
    name=REMOVE_ORPHAN.capability,
    display_name="Remove an orphaned Proxmox volume",
    description=(
        "Delete a Proxmox volume that belongs to no guest, verifying at execution rather "
        "than at proposal that nothing references it. A guest created between the two is "
        "exactly the volume nobody would think to re-check."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.DESTRUCTIVE,
    risk_class=class_of(REMOVE_ORPHAN.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "A whole disk image goes, permanently. It belongs to nobody only as far as anybody "
        "has checked, and there is no rollback."
    ),
    rollback_planner=DeclaredPlanner(REMOVE_ORPHAN),
    tags=("proxmox", "remediation", "storage", "orphan"),
    use_cases=(
        "reclaim a disk left behind when a guest was removed with its disks retained",
        "clear a volume that no guest configuration has referenced for a long time",
    ),
    anti_examples=(
        "removing a volume a guest created since the proposal was written",
        "removing a volume that is a replication base, which is a recovery point",
    ),
)
def proxmox_remove_orphaned_volume(node: str, datastore: str, volume: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        REMOVE_ORPHAN.capability, detail=f"removal of {volume} from {datastore} on {node}"
    )


__all__ = [
    "COMPONENTS",
    "DECLARED",
    "RECLAIM",
    "REMOVE_ORPHAN",
    "STORAGE_PRIVILEGES",
    "ReclamationPolicyRefused",
    "items_of",
    "proxmox_reclaim_storage",
    "proxmox_remove_orphaned_volume",
]
