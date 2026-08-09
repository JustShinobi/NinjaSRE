"""Moving a guest, and the two ways of doing it that are not the same act.

A manual migration is a move somebody asked for. An HA relocate is a change to
what the cluster's high-availability manager believes, and the manager then moves
things — possibly more than the one that was named, possibly again later. They
are separate capabilities because they are separate decisions, and the second is
the higher class for exactly that reason.

**Feasibility is checked first, and online is preferred.** A guest with a disk on
node-local storage, a passthrough device, or a datastore the receiving node
cannot reach is a guest that cannot move; Proxmox will accept the request and
fail at the far end, leaving the guest stopped. So the receiving node's view of
the guest's datastores is a precondition rather than a hope.

**An offline migration is refused, never substituted.** Falling back to stopping
the guest and moving it is a different action with a different cost, and
performing it under the name of the one that was approved is the substitution
this whole feature exists to prevent.
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
from config.constants.hypervisor import MIGRATION_SETTLE_SECONDS
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

#: What a migration snapshots. ``node`` is both what changes and what says the
#: guest is still where the approval said it was.
MOVEMENT_FIELDS: Final[tuple[str, ...]] = ("node", "status", "lock")

#: What the HA manager's view of one resource holds.
HA_FIELDS: Final[tuple[str, ...]] = ("ha_node", "ha_state", "ha_group")

MIGRATE_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="VM.Migrate",
        path="/vms",
        grants="move a guest to another node",
    ),
)

#: Proxmox gates its high-availability manager behind a node-level operational
#: privilege rather than a guest-level one, which is correct: relocating a
#: managed resource changes what the manager does to every resource it holds.
#: Declared as the privilege that certainly permits it — over-asking surfaces as
#: "your token needs more", where under-asking reports a token sufficient for a
#: job it cannot do.
HA_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="Sys.Console",
        path="/",
        grants="change what the high-availability manager holds about a resource",
    ),
)


def _migration_intent(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the state a migration intends: the guest, *running*, on the target node.

    Both halves. A migration that Proxmox accepted and that left the guest
    stopped at the far end has moved it and has not worked, and an intent naming
    only the node would call that a success.
    """
    del before
    return {"node": str(action.arguments.get("target", "")), "status": "running"}


def _relocation_intent(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
    """Return the state a relocation intends: the manager holding a new home for it."""
    del before
    return {
        "ha_node": str(action.arguments.get("target", "")),
        "ha_group": str(action.arguments.get("group", "")),
    }


MIGRATE = ProxmoxRemediation(
    capability="proxmox_migrate_guest",
    category=WriteCategory.MOVEMENT,
    endpoint="/nodes/{node}/{kind}/{vmid}/migrate",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
        Precondition.NODE_NOT_AMBIGUOUSLY_DEAD,
        Precondition.TARGET_NODE_SEES_STORAGE,
        Precondition.ONLINE_MIGRATION_POSSIBLE,
    ),
    rollback=RollbackDeclaration(
        summary="Migrate {target} back to the node it was on ({restored}).",
        steps=(
            "Check that the original node can still receive {target}.",
            "Migrate {target} back to it, online.",
            "Confirm it is running there and its services answer.",
        ),
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(name=signals.NODE_MEMORY_PERCENT, direction=SignalDirection.DOWN),
        ),
        settle_seconds=MIGRATION_SETTLE_SECONDS,
    ),
    privileges=MIGRATE_PRIVILEGES,
    fields=MOVEMENT_FIELDS,
    identity_fields=("node", "lock"),
    intent_of=_migration_intent,
    writes_configuration=True,
    assumes_node_is_dead=True,
    operation="qm migrate <vmid> <target> --online",
    arguments=("node", "vmid", "kind", "target"),
)

HA_RELOCATE = ProxmoxRemediation(
    capability="proxmox_ha_relocate",
    category=WriteCategory.HIGH_AVAILABILITY,
    endpoint="/cluster/ha/resources/{sid}",
    method="PUT",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.NODE_NOT_AMBIGUOUSLY_DEAD,
    ),
    rollback=RollbackDeclaration(
        summary="Write the manager's previous view of {target} back ({restored}).",
        steps=(
            "Set the resource's group and requested state back to what was recorded.",
            "Wait for the manager's next round and confirm it holds that view.",
            "Confirm the guest is running where the restored view puts it.",
        ),
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(name=signals.NODE_MEMORY_PERCENT, direction=SignalDirection.DOWN),
        ),
        settle_seconds=MIGRATION_SETTLE_SECONDS,
    ),
    privileges=HA_PRIVILEGES,
    fields=HA_FIELDS,
    identity_fields=("ha_node", "ha_state"),
    intent_of=_relocation_intent,
    writes_configuration=True,
    assumes_node_is_dead=True,
    operation="ha-manager set <sid> --group <group>",
    arguments=("sid", "target", "group"),
)

DECLARED: Final[tuple[ProxmoxRemediation, ...]] = (MIGRATE, HA_RELOCATE)

COMPONENTS: Final[tuple[RemediationComponents, ...]] = (
    components_for(MIGRATE),
    components_for(HA_RELOCATE),
)


@tool(
    name=MIGRATE.capability,
    display_name="Migrate a Proxmox guest",
    description=(
        "Move a Proxmox guest to another node online, after checking that the receiving node "
        "can see every datastore the guest has disks on. Refuses rather than falling back to "
        "an offline migration, and refuses in a two-node cluster whose other member is not "
        "answering, because nothing there distinguishes a dead node from an unreachable one."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(MIGRATE.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest pauses at the switch-over, both nodes and the link between them carry the "
        "memory copy, and a migration that fails at the far end leaves the guest stopped."
    ),
    rollback_planner=DeclaredPlanner(MIGRATE),
    tags=("proxmox", "remediation", "guest", "migration"),
    use_cases=(
        "move a guest off a node that is running out of memory",
        "empty a node before planned work on it",
    ),
    anti_examples=(
        "moving a guest whose disk the receiving node cannot see",
        "moving a guest off a node that is merely not answering",
    ),
)
def proxmox_migrate_guest(node: str, vmid: int, kind: str, target: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        MIGRATE.capability, detail=f"migration of {kind}/{vmid} from {node} to {target}"
    )


@tool(
    name=HA_RELOCATE.capability,
    display_name="Relocate a Proxmox high-availability resource",
    description=(
        "Change what the Proxmox high-availability manager holds about one resource, so it "
        "runs somewhere else. Distinct from a manual migration: the manager acts on its own "
        "schedule and may move other resources as a consequence."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    risk_class=class_of(HA_RELOCATE.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "This changes what the cluster's manager believes rather than moving one guest. It "
        "stops and starts the resource, and what else the manager then does follows from it."
    ),
    rollback_planner=DeclaredPlanner(HA_RELOCATE),
    tags=("proxmox", "remediation", "high-availability", "migration"),
    use_cases=(
        "move a managed resource off a node that is being taken out of service",
        "correct a resource pinned to a group whose nodes can no longer run it",
    ),
    anti_examples=(
        "relocating a resource away from a node that is merely unreachable",
        "using this where a manual migration would do, which is almost always",
    ),
)
def proxmox_ha_relocate(sid: str, target: str, group: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(
        HA_RELOCATE.capability, detail=f"relocation of {sid} to {target} via group {group}"
    )


__all__ = [
    "COMPONENTS",
    "DECLARED",
    "HA_FIELDS",
    "HA_PRIVILEGES",
    "HA_RELOCATE",
    "MIGRATE",
    "MIGRATE_PRIVILEGES",
    "MOVEMENT_FIELDS",
    "proxmox_ha_relocate",
    "proxmox_migrate_guest",
]
