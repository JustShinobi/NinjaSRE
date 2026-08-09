"""What may be done to a guest's own lifecycle, and what each of them costs.

Seven writes, for both kinds of guest — a container and a virtual machine differ
in their endpoints and in what their configuration means, and the kind travels as
an argument so an action does not have to exist twice.

Three of the seven carry the substance of this module.

**A graceful shutdown and a hard stop are different actions.** Asking a guest's
operating system to close its files is middle-risk and reversible by starting it
again. Cutting the power on a running database loses whatever it had not written,
and that is the top of the scale. Modelling them separately is what lets an
operator permit the first unattended and require approval for the second, which
is the posture most people actually want.

**A restart escalates, and the escalation is a second action.** ``reboot`` asks
politely and waits. When the guest has not gone after the declared timeout, the
escalation is the hard stop — proposed, classified, and recorded as its own act
rather than performed quietly under the name of the polite one.

**Clearing a lock requires the holder to be dead.** Not "the lock looks old", not
"the task list is empty": the task named in the lock is read and confirmed
finished. A lock cleared while its holder is running lets a second operation
start against a guest a live one is already changing, and there is no autonomy
level at which that is acceptable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from capabilities.tools.remediation import _base
from capabilities.tools.remediation.proxmox import signals
from capabilities.tools.remediation.proxmox.components import (
    DeclaredPlanner,
    RestartedVerifier,
    StartedVerifier,
    components_for,
)
from capabilities.tools.remediation.proxmox.declaration import (
    ProxmoxRemediation,
    RollbackDeclaration,
    WriteCategory,
)
from capabilities.tools.remediation.proxmox.preconditions import Precondition
from capabilities.tools.remediation.proxmox.risk import class_of
from config.constants.hypervisor import GUEST_SETTLE_SECONDS
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

#: What every guest write snapshots. ``uptime`` is here for the reboot, which is
#: the one action whose effect is invisible in any other field; ``node`` is here
#: for all of them, because a guest that migrated between the proposal and the
#: execution is a different target wearing the same number.
GUEST_FIELDS: Final[tuple[str, ...]] = ("node", "status", "lock", "uptime")

#: The subset that says the target is still the thing that was approved.
GUEST_IDENTITY: Final[tuple[str, ...]] = ("node", "lock")

#: What a start additionally snapshots. A guest that reached ``running`` and
#: whose own agent does not answer is a guest that booted and did not come up,
#: and only the agent can tell the two apart — so the start is the one action
#: that reads it. ``None`` means the guest declares no agent, which is a
#: different fact from an agent that did not reply.
START_FIELDS: Final[tuple[str, ...]] = (*GUEST_FIELDS, "agent_responds")

#: What a token has to hold to change a guest's power state. One privilege for
#: the lot of them, which is Proxmox's own granularity.
POWER_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="VM.PowerMgmt",
        path="/vms",
        grants="start, stop, shut down, reboot, suspend and resume guests",
    ),
)

#: What a token has to hold to edit a guest's configuration, which is how a lock
#: is cleared and put back.
CONFIG_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="VM.Config.Options",
        path="/vms",
        grants="edit a guest's configuration, which is how a lock is cleared",
    ),
)

_RUNNING = VerificationDeclaration(
    signals=(
        VerificationSignal(
            name=signals.GUEST_RUNNING,
            direction=SignalDirection.UP,
            # One is the whole scale: the guest is running or it is not.
            clears_at=1.0,
        ),
    ),
    settle_seconds=GUEST_SETTLE_SECONDS,
)

_NODE_RELIEVED = VerificationDeclaration(
    signals=(VerificationSignal(name=signals.NODE_MEMORY_PERCENT, direction=SignalDirection.DOWN),),
    settle_seconds=GUEST_SETTLE_SECONDS,
)


def _intent(**values: Any) -> Any:
    """Return an intent function that always asks for ``values``.

    A factory rather than seven closures written out, because the difference
    between "the guest should be running" and "the guest should be stopped" is
    the value and nothing else.
    """

    def of(action: RemediationAction, before: StateSnapshot) -> Mapping[str, Any]:
        """Return the state this action intends to leave behind."""
        del action, before
        return dict(values)

    return of


# --- The seven declarations ---------------------------------------------------

START = ProxmoxRemediation(
    capability="proxmox_start_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/start",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    ),
    rollback=RollbackDeclaration(
        summary="Shut {target} down again, returning it to the state it was in ({restored}).",
        steps=(
            "Ask {target}'s own operating system to shut down, and wait for it.",
            "Confirm {target} reports itself stopped.",
        ),
        performed_by="proxmox_shutdown_guest",
    ),
    verification=_RUNNING,
    privileges=POWER_PRIVILEGES,
    fields=START_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="running"),
    writes_configuration=True,
    operation="pct start <vmid> / qm start <vmid>",
    arguments=("node", "vmid", "kind"),
)

SHUTDOWN = ProxmoxRemediation(
    capability="proxmox_shutdown_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/shutdown",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    ),
    rollback=RollbackDeclaration(
        summary="Start {target} again. It was running before this ({restored}).",
        steps=(
            "Start {target} on the node it was running on.",
            "Confirm it reached a running state and its services answer.",
        ),
        performed_by="proxmox_start_guest",
    ),
    verification=_NODE_RELIEVED,
    privileges=POWER_PRIVILEGES,
    fields=GUEST_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="stopped"),
    writes_configuration=True,
    operation="pct shutdown <vmid> / qm shutdown <vmid>",
    arguments=("node", "vmid", "kind"),
)

REBOOT = ProxmoxRemediation(
    capability="proxmox_reboot_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/reboot",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    ),
    rollback=RollbackDeclaration(
        summary=(
            "A reboot of {target} cannot be undone: the previous process tree is gone and "
            "its in-flight work with it."
        ),
        steps=(
            "Confirm {target} came back and its services answer.",
            "If it did not, start it explicitly rather than rebooting a second time.",
            "Re-read the signal that prompted this, to see whether it moved.",
        ),
        reversible=False,
        performed_by="proxmox_start_guest",
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(
                name=signals.GUEST_RESTARTS_PER_HOUR,
                direction=SignalDirection.DOWN,
                # This reboot is one of them. More than one an hour afterwards is
                # the guest failing again rather than the deployment's own doing.
                clears_at=1.0,
            ),
        ),
        settle_seconds=GUEST_SETTLE_SECONDS,
    ),
    privileges=POWER_PRIVILEGES,
    fields=GUEST_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="running", uptime=0),
    writes_configuration=True,
    operation="pct reboot <vmid> / qm reboot <vmid>",
    arguments=("node", "vmid", "kind"),
)

STOP = ProxmoxRemediation(
    capability="proxmox_stop_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/stop",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
    ),
    rollback=RollbackDeclaration(
        summary=(
            "Starting {target} again is a recovery, not a reversal: what it had not written "
            "when the power went is gone."
        ),
        steps=(
            "Start {target} and watch it come up, because a hard stop can leave a dirty "
            "filesystem that the guest will check on boot.",
            "Confirm its services answer, and look for corruption before declaring it well.",
        ),
        reversible=False,
        performed_by="proxmox_start_guest",
    ),
    verification=_NODE_RELIEVED,
    privileges=POWER_PRIVILEGES,
    fields=GUEST_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="stopped"),
    writes_configuration=True,
    operation="pct stop <vmid> / qm stop <vmid>",
    arguments=("node", "vmid", "kind"),
)

SUSPEND = ProxmoxRemediation(
    capability="proxmox_suspend_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/suspend",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    ),
    rollback=RollbackDeclaration(
        summary="Resume {target} from the memory image this wrote ({restored}).",
        steps=(
            "Resume {target} on the node holding its memory image.",
            "Confirm it is running and its services answer.",
        ),
        performed_by="proxmox_resume_guest",
    ),
    verification=_NODE_RELIEVED,
    privileges=POWER_PRIVILEGES,
    fields=GUEST_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="paused"),
    writes_configuration=True,
    operation="qm suspend <vmid>",
    arguments=("node", "vmid", "kind"),
)

RESUME = ProxmoxRemediation(
    capability="proxmox_resume_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/status/resume",
    method="POST",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    ),
    rollback=RollbackDeclaration(
        summary="Suspend {target} again, returning it to the state it was in ({restored}).",
        steps=(
            "Suspend {target}, which writes its memory image back out.",
            "Confirm it reports itself paused.",
        ),
        performed_by="proxmox_suspend_guest",
    ),
    verification=_RUNNING,
    privileges=POWER_PRIVILEGES,
    fields=GUEST_FIELDS,
    identity_fields=GUEST_IDENTITY,
    intent_of=_intent(status="running"),
    writes_configuration=True,
    operation="qm resume <vmid>",
    arguments=("node", "vmid", "kind"),
)

UNLOCK = ProxmoxRemediation(
    capability="proxmox_unlock_guest",
    category=WriteCategory.GUEST_LIFECYCLE,
    endpoint="/nodes/{node}/{kind}/{vmid}/config",
    method="PUT",
    preconditions=(
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.HOLDING_TASK_DEAD,
    ),
    rollback=RollbackDeclaration(
        summary="Write the lock back onto {target} exactly as it was ({restored}).",
        steps=(
            "Set {target}'s lock to the value recorded before it was cleared.",
            "Confirm the guest reports that lock again.",
        ),
    ),
    verification=VerificationDeclaration(
        signals=(
            VerificationSignal(
                name=signals.GUEST_LOCKED,
                direction=SignalDirection.DOWN,
                # Zero locks is the whole of the effect, and it is a fact rather
                # than a movement — which is what makes ``ineffective`` sayable.
                clears_at=0.0,
            ),
        ),
        settle_seconds=GUEST_SETTLE_SECONDS,
    ),
    privileges=CONFIG_PRIVILEGES,
    fields=GUEST_FIELDS,
    # The lock is what this action changes, so it cannot also be what says the
    # target is unchanged — the identity here is where the guest lives.
    identity_fields=("node",),
    intent_of=_intent(lock=""),
    writes_configuration=True,
    operation="pct unlock <vmid> / qm unlock <vmid>",
    arguments=("node", "vmid", "kind"),
)

DECLARED: Final[tuple[ProxmoxRemediation, ...]] = (
    START,
    SHUTDOWN,
    REBOOT,
    STOP,
    SUSPEND,
    RESUME,
    UNLOCK,
)

COMPONENTS: Final[tuple[RemediationComponents, ...]] = (
    components_for(START, verifier=StartedVerifier()),
    components_for(SHUTDOWN),
    components_for(REBOOT, verifier=RestartedVerifier()),
    components_for(STOP),
    components_for(SUSPEND),
    components_for(RESUME),
    components_for(UNLOCK),
)


# --- The agent-callable surface -----------------------------------------------
#
# Every one of these refuses. A remediation capability is not callable directly:
# it runs through the remediation gate, which records the approval and the
# rollback plan before anything changes. The refusal is what makes "every write
# went through the gate" true of every entry point rather than of the ones
# somebody remembered.


@tool(
    name=START.capability,
    display_name="Start a Proxmox guest",
    description=(
        "Start a stopped Proxmox container or virtual machine and confirm it reached a "
        "running state, including that its guest agent answers where one is present. "
        "Refused when the cluster has no quorum or the guest is locked."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(START.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "Starting a guest commits the node's memory and disk to it, and a guest that was "
        "stopped deliberately is one somebody stopped for a reason."
    ),
    rollback_planner=DeclaredPlanner(START),
    tags=("proxmox", "remediation", "guest", "lifecycle"),
    use_cases=(
        "bring back a guest that a failed host reboot left stopped",
        "start a container whose start was blocked by a datastore that has since returned",
    ),
    anti_examples=(
        "starting a guest whose disk is on a datastore that is still unreachable",
        "starting a guest that was stopped deliberately, before finding out why",
    ),
)
def proxmox_start_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(START.capability, detail=f"start of {kind}/{vmid} on {node}")


@tool(
    name=SHUTDOWN.capability,
    display_name="Shut down a Proxmox guest",
    description=(
        "Ask a Proxmox guest's own operating system to shut down, waiting for it to close "
        "its files. Never escalates to a hard stop on its own — that is a separate action "
        "with a separate risk class."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(SHUTDOWN.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest stops serving, entirely, until somebody starts it again. Whatever depends "
        "on it stops with it."
    ),
    rollback_planner=DeclaredPlanner(SHUTDOWN),
    tags=("proxmox", "remediation", "guest", "lifecycle"),
    use_cases=(
        "free a node's memory by stopping a guest that is not needed right now",
        "stop a guest cleanly before its node is worked on",
    ),
    anti_examples=(
        "stopping a guest to clear a symptom whose cause is unknown",
        "hard-stopping a guest that is merely slow to shut down",
    ),
)
def proxmox_shutdown_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(SHUTDOWN.capability, detail=f"shutdown of {kind}/{vmid} on {node}")


@tool(
    name=REBOOT.capability,
    display_name="Reboot a Proxmox guest",
    description=(
        "Reboot a Proxmox guest through its own operating system. A guest that has not gone "
        "after the declared timeout is not hard-stopped here: the escalation is a separate, "
        "separately classified action."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
    risk_class=class_of(REBOOT.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest's processes and their in-flight work are destroyed, along with the state "
        "that would have explained the failure. Neither is recoverable."
    ),
    rollback_planner=DeclaredPlanner(REBOOT),
    tags=("proxmox", "remediation", "guest", "restart"),
    use_cases=(
        "recover a guest whose services have become unusable, after the cause is known",
        "apply a change inside a guest that only takes effect on restart",
    ),
    anti_examples=(
        "rebooting before the cause is understood, which destroys the evidence",
        "rebooting a guest whose failure will recur immediately",
    ),
)
def proxmox_reboot_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(REBOOT.capability, detail=f"reboot of {kind}/{vmid} on {node}")


@tool(
    name=STOP.capability,
    display_name="Hard-stop a Proxmox guest",
    description=(
        "Stop a Proxmox guest immediately, without telling anything inside it. The hardware "
        "equivalent of pulling the power: anything the guest had not written is gone. This "
        "is the escalation a reboot proposes when a graceful shutdown does not complete."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.DESTRUCTIVE,
    risk_class=class_of(STOP.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "Nothing inside the guest is told. Unflushed writes are lost, and a database or a "
        "filesystem may come back needing repair."
    ),
    rollback_planner=DeclaredPlanner(STOP),
    tags=("proxmox", "remediation", "guest", "lifecycle"),
    use_cases=(
        "stop a guest that did not respond to a graceful shutdown within its declared timeout",
        "stop a guest that is taking a node down with it",
    ),
    anti_examples=(
        "stopping a guest that is shutting down cleanly and slowly",
        "using this where a graceful shutdown has not been tried",
    ),
)
def proxmox_stop_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(STOP.capability, detail=f"hard stop of {kind}/{vmid} on {node}")


@tool(
    name=SUSPEND.capability,
    display_name="Suspend a Proxmox guest",
    description=(
        "Suspend a Proxmox guest, writing its memory image to disk so it can be resumed "
        "exactly where it left off. Needs room on the datastore for the image."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(SUSPEND.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest stops serving until it is resumed, and writing its memory image needs "
        "space on a datastore that may not have it."
    ),
    rollback_planner=DeclaredPlanner(SUSPEND),
    tags=("proxmox", "remediation", "guest", "lifecycle"),
    use_cases=(
        "free a node's memory without losing the state inside a guest",
        "pause a guest that is contending for a disk something more urgent needs",
    ),
    anti_examples=(
        "suspending a guest onto a datastore with no room for its memory image",
        "suspending a guest that is serving traffic somebody depends on",
    ),
)
def proxmox_suspend_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(SUSPEND.capability, detail=f"suspend of {kind}/{vmid} on {node}")


@tool(
    name=RESUME.capability,
    display_name="Resume a Proxmox guest",
    description=(
        "Resume a suspended Proxmox guest from the memory image it was suspended with, and "
        "confirm it reached a running state."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(RESUME.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "The guest starts serving again and takes back the memory its suspension released."
    ),
    rollback_planner=DeclaredPlanner(RESUME),
    tags=("proxmox", "remediation", "guest", "lifecycle"),
    use_cases=(
        "bring back a guest suspended to relieve a node that has since recovered",
        "resume a guest after the work its suspension made room for has finished",
    ),
    anti_examples=(
        "resuming a guest onto a node that still has no memory for it",
        "resuming a guest whose datastore is still unreachable",
    ),
)
def proxmox_resume_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(RESUME.capability, detail=f"resume of {kind}/{vmid} on {node}")


@tool(
    name=UNLOCK.capability,
    display_name="Clear an orphaned Proxmox guest lock",
    description=(
        "Clear the lock a dead task left on a Proxmox guest, so the guest is manageable "
        "again. Refuses unless the task named in the lock is confirmed finished — a lock "
        "cleared while its holder is running lets a second operation start against a guest "
        "a live one is already changing."
    ),
    domain="remediation",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    risk_class=class_of(UNLOCK.capability).value,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "A lock is what stops two operations changing one guest at once. Clearing one whose "
        "holder is still alive is how a guest ends up with two writers."
    ),
    rollback_planner=DeclaredPlanner(UNLOCK),
    tags=("proxmox", "remediation", "guest", "lock"),
    use_cases=(
        "free a guest a backup left locked when the backup process died",
        "make a guest manageable again after a migration was interrupted",
    ),
    anti_examples=(
        "clearing a lock whose task is still running",
        "clearing a lock to work around a backup that keeps failing",
    ),
)
def proxmox_unlock_guest(node: str, vmid: int, kind: str) -> CapabilityResult:
    """Return the refusal that sends this call through the remediation gate."""
    return _base.refuse(UNLOCK.capability, detail=f"unlock of {kind}/{vmid} on {node}")


__all__ = [
    "COMPONENTS",
    "CONFIG_PRIVILEGES",
    "DECLARED",
    "GUEST_FIELDS",
    "GUEST_IDENTITY",
    "POWER_PRIVILEGES",
    "REBOOT",
    "START_FIELDS",
    "RESUME",
    "START",
    "STOP",
    "SHUTDOWN",
    "SUSPEND",
    "UNLOCK",
    "proxmox_reboot_guest",
    "proxmox_resume_guest",
    "proxmox_shutdown_guest",
    "proxmox_start_guest",
    "proxmox_stop_guest",
    "proxmox_suspend_guest",
    "proxmox_unlock_guest",
]
