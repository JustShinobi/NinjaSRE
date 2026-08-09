"""Every hypervisor write, and how the laboratory runs it for real at least once.

The fixture suite scores what the system *proposes*. That is the right measure
for a decision and it says nothing about whether the write works — whether the
task Proxmox starts succeeds, whether the rollback plan reverses what happened,
whether the verification signal moves. Those are answered by doing it, and there
is exactly one place doing it is acceptable.

So this is a second, smaller obligation with its own coverage test: thirteen
writes, thirteen rehearsals, each naming the target it acts on, the state that
has to hold before it runs, and how the laboratory is put back afterwards. A
capability added to feature 046 without a rehearsal fails here, which is the
point — an action that has never once been run against real hardware is not an
action anybody should let run unattended.

The declarations load and are checked everywhere, including on a laptop with no
cluster. Only executing them needs the laboratory.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from tests.harness.proxmox.declaration import declared_capabilities


@dataclass(frozen=True, slots=True)
class Rehearsal:
    """One write, and what the laboratory does to run it and undo it.

    ``expects`` is the reading that says it worked, in the words the shipped
    verification declaration uses. Writing it here rather than deriving it keeps
    the rehearsal reviewable: somebody reading this file can say whether the
    check is the right one without opening the capability.
    """

    capability: str
    target: str
    #: What has to be true before this may run. The same preconditions the
    #: capability evaluates, restated so a reader can see what the laboratory has
    #: to arrange rather than what the code happens to check.
    given: str
    #: What the laboratory does to set that up.
    arrange: str
    #: The reading that says the write took effect.
    expects: str
    #: How the cluster is returned to its known state afterwards.
    restore: str

    def __post_init__(self) -> None:
        for name in ("capability", "target", "given", "arrange", "expects", "restore"):
            if not str(getattr(self, name)).strip():
                raise ValueError(
                    f"{self.capability or 'a rehearsal'}: {name} is blank, so this rehearsal "
                    f"describes a write nobody could run or undo."
                )


#: The thirteen, in the order of the risk table: least dangerous first, because
#: that is the order the laboratory should run them in and the order that makes
#: an out-of-place entry visible.
REHEARSALS: Final[tuple[Rehearsal, ...]] = (
    Rehearsal(
        capability="proxmox_unlock_guest",
        target="ct:9101 on lab02",
        given="the guest holds a lock and no task of its own is running",
        arrange="start a vzdump of ct:9101 and kill the task without letting it clean up",
        expects="the guest's configuration no longer carries a lock and an ordinary "
        "status read succeeds",
        restore="roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_start_guest",
        target="ct:9102 on lab02",
        given="the guest is stopped and its datastore is reachable",
        arrange="shut ct:9102 down cleanly and wait for it to report stopped",
        expects="the guest reports running and its own service answers",
        restore="shut it down again and roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_resume_guest",
        target="vm:9201 on lab02",
        given="the guest is suspended and its memory image is readable",
        arrange="suspend vm:9201 to disk and confirm the image was written",
        expects="the guest reports running with the uptime it had before the suspend",
        restore="roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_shutdown_guest",
        target="ct:9102 on lab02",
        given="the guest is running and nothing holds a lock on it",
        arrange="confirm ct:9102 is running and unlocked",
        expects="the guest reports stopped and the shutdown task exited OK",
        restore="start it again and roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_reboot_guest",
        target="ct:9102 on lab02",
        given="the guest is running and its shutdown is expected to be graceful",
        arrange="confirm ct:9102 is running with no in-flight task",
        expects="the guest's uptime resets and the graceful shutdown is recorded "
        "separately from any hard stop",
        restore="roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_suspend_guest",
        target="vm:9201 on lab02",
        given="the guest is running and its datastore has room for the memory image",
        arrange="confirm free space on the datastore exceeds the guest's memory",
        expects="the guest reports suspended and the memory image exists on the datastore",
        restore="resume it and roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_migrate_guest",
        target="ct:9103, from lab02 to lab01",
        given="the cluster is quorate and the guest's disk is on shared storage",
        arrange="place ct:9103's rootfs on the shared datastore both nodes declare",
        expects="the cluster resource list reports the guest on lab01 and it is still running",
        restore="migrate it back and roll both nodes to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_retry_backup",
        target="the vzdump job covering ct:9102 on lab02",
        given="the job exists, is enabled, and its last run failed",
        arrange="point the job at a datastore that is full, let it fail, then free the space",
        expects="a new vzdump task exits OK and a backup appears on the datastore",
        restore="prune the backup and roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_resync_replication",
        target="the replication job for ct:9103, lab02 to lab01",
        given="the job is enabled and its last synchronisation is older than its schedule",
        arrange="disable the job, write inside the guest, and re-enable it",
        expects="the job's last synchronisation moves to now and its exposure returns to zero",
        restore="roll both nodes to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_ha_relocate",
        target="the HA resource ct:9104",
        given="the cluster is quorate and the HA manager holds its lock",
        arrange="add ct:9104 to an HA group covering both nodes",
        expects="the manager's requested state names the new node and the resource follows it",
        restore="remove the HA resource and roll both nodes to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_stop_guest",
        target="ct:9105 on lab02, which holds nothing anybody wants",
        given="the guest is running and its filesystem carries only rehearsal data",
        arrange="write a marker file inside ct:9105 and do not sync it",
        expects="the guest reports stopped and the unflushed marker is gone, which is the "
        "cost this action's classification is about",
        restore="roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_reclaim_storage",
        target="a backup of ct:9105 on the laboratory datastore",
        given="the item is a recovery point and the approval for its deletion was granted",
        arrange="take a vzdump of ct:9105 so there is a recovery point to delete",
        expects="the datastore's content list no longer holds the volume and its free "
        "space rises by the volume's size",
        restore="take the backup again and roll lab02 back to the scenario-baseline snapshot",
    ),
    Rehearsal(
        capability="proxmox_remove_orphaned_volume",
        target="a disk left behind on lab02's local storage",
        given="no guest in the cluster resource list references the volume",
        arrange="create ct:9106, note its volume, and remove the guest configuration only",
        expects="the volume is absent from the datastore's content list and no guest lost a disk",
        restore="roll lab02 back to the scenario-baseline snapshot",
    ),
)

_BY_CAPABILITY: Final[dict[str, Rehearsal]] = {found.capability: found for found in REHEARSALS}


def rehearsal_for(capability: str) -> Rehearsal:
    """Return how the laboratory exercises ``capability``.

    Raises:
        KeyError: no rehearsal exists, which is a write nobody has ever run
            against hardware.
    """
    found = _BY_CAPABILITY.get(capability)
    if found is None:
        raise KeyError(
            f"{capability!r} has no laboratory rehearsal, so it has never been run against real "
            f"hardware. Rehearsed: {', '.join(sorted(_BY_CAPABILITY))}."
        )
    return found


def unrehearsed() -> tuple[str, ...]:
    """Return every declared hypervisor write with no rehearsal, in name order."""
    return tuple(sorted(declared_capabilities() - set(_BY_CAPABILITY)))


def unknown_rehearsals() -> tuple[str, ...]:
    """Return every rehearsal for something this deployment does not declare.

    The other direction, and the one that goes stale silently: a capability
    removed from feature 046 leaves a rehearsal that would be run against the
    laboratory and would fail for a reason nobody could act on.
    """
    return tuple(sorted(set(_BY_CAPABILITY) - declared_capabilities()))


def describe(rehearsals: Sequence[Rehearsal] = REHEARSALS) -> str:
    """Return the block a laboratory report prints before it starts."""
    return "\n".join(
        f"{found.capability} on {found.target}\n"
        f"    given: {found.given}\n"
        f"    arrange: {found.arrange}\n"
        f"    expects: {found.expects}\n"
        f"    restore: {found.restore}"
        for found in rehearsals
    )


__all__ = [
    "REHEARSALS",
    "Rehearsal",
    "describe",
    "rehearsal_for",
    "unknown_rehearsals",
    "unrehearsed",
]
