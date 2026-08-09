"""What has to be true right now, checked against a reading taken right now.

An investigation that took four minutes has a four-minute-old picture. The guest
may have migrated, the lock may have been taken by live work, the datastore may
have filled, the node the plan assumed was dead may have come back. Every
precondition here is evaluated against a fresh reading immediately before the
write, and a changed target is a refusal rather than a proceed.

**Evaluation is pure and the reading is not.** ``Facts`` is a value somebody else
gathered; everything below is a function of it. That split is what makes the
two-node ambiguity and the quorum refusal exhaustively testable without a
hypervisor, which is the only way anybody was ever going to test them.

**Every unmet precondition is reported, never the first.** An operator widening a
proposal wants to see all of them. Fixing one and re-running to discover the next
is how a refusal gets argued with one clause at a time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from capabilities.tools.remediation.proxmox.risk import ReclaimableItem
from config.constants.hypervisor import (
    BACKUP_COLLISION_WINDOW_SECONDS,
    QUORUM_AMBIGUITY_NODE_COUNT,
)
from integrations.proxmox.models import TaskRecord
from platform.remediation.errors import RemediationError
from platform.remediation.models import StateSnapshot


class Precondition(StrEnum):
    """One thing that has to hold before a write, named so a declaration can list it."""

    #: The target still looks the way the approval was granted against.
    TARGET_UNCHANGED = "target_unchanged"
    #: The task holding the guest's lock has been confirmed finished.
    HOLDING_TASK_DEAD = "holding_task_dead"
    #: The guest carries no lock at all, which is what every write but the
    #: unlock itself needs.
    GUEST_UNLOCKED = "guest_unlocked"
    #: The cluster has quorum, without which the configuration filesystem is
    #: read-only and no configuration write can land.
    CLUSTER_QUORATE = "cluster_quorate"
    #: The action does not have to assume an unreachable node is dead.
    NODE_NOT_AMBIGUOUSLY_DEAD = "node_not_ambiguously_dead"
    #: The node the guest would move to can see every datastore its disks are on.
    TARGET_NODE_SEES_STORAGE = "target_node_sees_storage"
    #: The move can be made online, rather than by stopping the guest.
    ONLINE_MIGRATION_POSSIBLE = "online_migration_possible"
    #: No scheduled backup run is close enough to collide with this one.
    NO_SCHEDULED_BACKUP_COLLISION = "no_scheduled_backup_collision"
    #: Every volume named belongs to no guest, checked now rather than at proposal.
    VOLUME_BELONGS_TO_NO_GUEST = "volume_belongs_to_no_guest"
    #: No backup currently running is about to need the space being reclaimed.
    NO_RUNNING_BACKUP_NEEDS_THE_SPACE = "no_running_backup_needs_the_space"
    #: Nothing being deleted is a backup, when the reason for deleting is a backup.
    NOT_DELETING_A_BACKUP_TO_MAKE_ROOM = "not_deleting_a_backup_to_make_room"

    def describe(self) -> str:
        """Return the sentence a proposal shows beside this precondition."""
        return _DESCRIPTIONS[self]


_DESCRIPTIONS: Final[dict[Precondition, str]] = {
    Precondition.TARGET_UNCHANGED: "the target still looks the way the approval was given against",
    Precondition.HOLDING_TASK_DEAD: "the task holding the lock has been confirmed finished",
    Precondition.GUEST_UNLOCKED: "the guest carries no lock",
    Precondition.CLUSTER_QUORATE: "the cluster has quorum, so its configuration is writable",
    Precondition.NODE_NOT_AMBIGUOUSLY_DEAD: (
        "no node has to be assumed dead on evidence that cannot tell dead from unreachable"
    ),
    Precondition.TARGET_NODE_SEES_STORAGE: "the receiving node can see every disk the guest has",
    Precondition.ONLINE_MIGRATION_POSSIBLE: "the guest can move without being stopped",
    Precondition.NO_SCHEDULED_BACKUP_COLLISION: "no scheduled backup run is about to start",
    Precondition.VOLUME_BELONGS_TO_NO_GUEST: "every volume named is referenced by no guest",
    Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE: (
        "no backup currently running is about to need the space"
    ),
    Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM: (
        "nothing being deleted is a backup taken to make room for a backup"
    ),
}


@dataclass(frozen=True, slots=True)
class Facts:
    """One fresh reading of everything a precondition could ask about.

    A single value rather than a client, because evaluation is pure. What is read
    is decided by what a capability declared, so a guest start never pays for a
    datastore listing — the gatherer takes the declaration and asks for no more
    than it names.
    """

    #: Membership and quorum.
    quorate: bool = True
    is_clustered: bool = True
    members: tuple[str, ...] = ()
    online_nodes: tuple[str, ...] = ()
    contributing_quorum_device: bool = False

    #: The guest, as it stands now.
    guest_node: str = ""
    guest_status: str = ""
    guest_lock: str = ""
    holding_task: TaskRecord | None = None

    #: Movement.
    target_node: str = ""
    target_node_datastores: tuple[str, ...] = ()
    guest_datastores: tuple[str, ...] = ()
    online_migration_blocker: str = ""

    #: Backups and replication.
    seconds_until_scheduled_backup: int | None = None
    running_backup_bytes_needed: int = 0
    free_bytes: int = 0

    #: Storage.
    items: tuple[ReclaimableItem, ...] = ()
    volume_owners: Mapping[str, int] = field(default_factory=dict)
    making_room_for_a_backup: bool = False

    #: The identity of the target, read now: the fields that say it is still the
    #: thing the approval was given for. ``None`` when it could not be read.
    #:
    #: A subset of what the snapshot holds, deliberately. A running guest's
    #: uptime changes every second, so comparing the whole snapshot would refuse
    #: every action against every running guest — which is a check that is right
    #: about nothing and fires on everything.
    identity: Mapping[str, Any] | None = None

    @property
    def two_node_ambiguity(self) -> bool:
        """Return whether this cluster cannot tell a dead node from an unreachable one.

        True only when it is genuinely undecidable: a clustered deployment of
        exactly two members, no quorum device contributing a vote, and a member
        not answering. A three-node cluster votes its way out of this, and a
        standalone installation has no peer to be wrong about.
        """
        if not self.is_clustered or self.contributing_quorum_device:
            return False
        if len(self.members) != QUORUM_AMBIGUITY_NODE_COUNT:
            return False
        return len(self.online_nodes) < len(self.members)


@dataclass(frozen=True, slots=True)
class Refusal:
    """One precondition that does not hold, and the sentence that says why."""

    precondition: Precondition
    reason: str

    def describe(self) -> str:
        """Return the line an operator reads in the refusal."""
        return f"{self.precondition.value}: {self.reason}"


class PreconditionRefused(RemediationError):
    """A write was refused because a precondition did not hold at execution time.

    Raised rather than returned, and raised *before* anything is written, so a
    refusal and a partial change are never the same outcome. The unmet
    preconditions are carried in full: an operator fixing one and re-running to
    discover the next is how a refusal is argued with one clause at a time.
    """

    def __init__(self, capability: str, target: str, refusals: Sequence[Refusal]) -> None:
        listed = "\n  - ".join(refusal.describe() for refusal in refusals)
        super().__init__(
            f"{capability!r} against {target!r} was refused before it ran, because the "
            f"following did not hold when it was checked:\n  - {listed}"
        )
        self.capability = capability
        self.target = target
        self.refusals = tuple(refusals)

    @property
    def names(self) -> tuple[str, ...]:
        """Return the preconditions that refused, in the order they were evaluated."""
        return tuple(refusal.precondition.value for refusal in self.refusals)


def evaluate(
    declared: Sequence[Precondition],
    *,
    facts: Facts,
    before: StateSnapshot,
) -> tuple[Refusal, ...]:
    """Return every declared precondition that does not hold against ``facts``.

    ``before`` is the state the approval was granted against. It is compared
    rather than trusted: an action approved four minutes ago against a guest that
    has since migrated is an action approved for something else.
    """
    refusals: list[Refusal] = []
    for precondition in declared:
        check = _CHECKS[precondition]
        reason = check(facts, before)
        if reason:
            refusals.append(Refusal(precondition=precondition, reason=reason))
    return tuple(refusals)


def _target_unchanged(facts: Facts, before: StateSnapshot) -> str:
    """Return why the target is not what it was, or the empty string when it is."""
    identity = facts.identity
    if identity is None:
        return (
            "the target could not be read immediately before the write, so nothing can "
            "confirm it is still the thing that was approved"
        )
    if not before.known:
        return (
            "the state this action was approved against was never read, so there is nothing "
            "to compare the current reading with"
        )
    moved = [
        f"{name} was {before.values.get(name)!r} and is now {value!r}"
        for name, value in sorted(identity.items())
        if before.values.get(name) != value
    ]
    if not moved:
        return ""
    return (
        f"the target changed after the action was proposed: {'; '.join(moved)}. The approval "
        f"was given for the earlier state, and this is a different action against the same name."
    )


def _holding_task_dead(facts: Facts, before: StateSnapshot) -> str:
    """Return why the lock's holder cannot be treated as dead, or the empty string."""
    del before
    if not facts.guest_lock:
        return ""
    task = facts.holding_task
    if task is None:
        return (
            f"the guest is locked by {facts.guest_lock!r} and no task was found holding it, so "
            f"whether the work is still running is unknown. Clearing a lock whose holder is "
            f"alive corrupts whatever it is doing."
        )
    if not task.finished:
        return (
            f"the task {task.upid} holding the {facts.guest_lock!r} lock is still running. "
            f"Clearing the lock now would let a second operation start against a guest a live "
            f"one is already changing."
        )
    return ""


def _guest_unlocked(facts: Facts, before: StateSnapshot) -> str:
    """Return why a lock blocks this write, or the empty string when none does."""
    del before
    if not facts.guest_lock:
        return ""
    return (
        f"the guest is locked by {facts.guest_lock!r}, so Proxmox will refuse this write. The "
        f"lock is cleared deliberately, by the unlock action, once its holder is confirmed dead."
    )


def _cluster_quorate(facts: Facts, before: StateSnapshot) -> str:
    """Return why a configuration write cannot land, or the empty string."""
    del before
    if facts.quorate or not facts.is_clustered:
        return ""
    return (
        "the cluster has no quorum, so its configuration filesystem is mounted read-only and "
        "no guest can be started, stopped, migrated or reconfigured on any node. Quorum has "
        "to return before this is possible, and returning it is a person's decision."
    )


def _node_not_ambiguously_dead(facts: Facts, before: StateSnapshot) -> str:
    """Return why the dead-node assumption is unsafe here, or the empty string."""
    del before
    if not facts.two_node_ambiguity:
        return ""
    missing = ", ".join(sorted(set(facts.members) - set(facts.online_nodes))) or "a member"
    return (
        f"this is a two-node cluster with no contributing quorum device, and {missing} is not "
        f"answering. Nothing available here distinguishes a node that is dead from one that is "
        f"merely unreachable, and both wrong answers cost data: acting on the first while the "
        f"second is true starts guests that are already running. This is reported and escalated "
        f"rather than resolved."
    )


def _target_node_sees_storage(facts: Facts, before: StateSnapshot) -> str:
    """Return which of the guest's datastores the receiving node cannot see."""
    del before
    if not facts.target_node:
        return "no receiving node was named, so nothing could be checked against one"
    unseen = sorted(set(facts.guest_datastores) - set(facts.target_node_datastores))
    if not unseen:
        return ""
    return (
        f"{facts.target_node} cannot see {', '.join(unseen)}, which the guest has disks on. "
        f"Proxmox would accept the migration and fail at the far end, leaving the guest stopped."
    )


def _online_migration_possible(facts: Facts, before: StateSnapshot) -> str:
    """Return why the move cannot be made online, or the empty string when it can."""
    del before
    if not facts.online_migration_blocker:
        return ""
    return (
        f"the guest cannot move without being stopped: {facts.online_migration_blocker}. An "
        f"offline migration is a different action with a different cost, and it is refused here "
        f"rather than performed quietly under the name of the one that was approved."
    )


def _no_scheduled_backup_collision(facts: Facts, before: StateSnapshot) -> str:
    """Return why a retry would collide with the schedule, or the empty string."""
    del before
    due = facts.seconds_until_scheduled_backup
    if due is None or due > BACKUP_COLLISION_WINDOW_SECONDS:
        return ""
    return (
        f"a scheduled backup run starts in {due}s, inside the "
        f"{BACKUP_COLLISION_WINDOW_SECONDS}s collision window. Two vzdump runs against one "
        f"guest contend for the same lock and the same datastore, and the scheduled one is the "
        f"one somebody depends on."
    )


def _volume_belongs_to_no_guest(facts: Facts, before: StateSnapshot) -> str:
    """Return which named volumes are still referenced by a guest."""
    del before
    owned = sorted(
        f"{item.volume_id} belongs to guest {facts.volume_owners[item.volume_id]}"
        for item in facts.items
        if item.volume_id in facts.volume_owners
    )
    if not owned:
        return ""
    return (
        f"{'; '.join(owned)}. Ownership is read at execution rather than at proposal, because a "
        f"guest created since the proposal is exactly the volume nobody would think to re-check."
    )


def _no_running_backup_needs_the_space(facts: Facts, before: StateSnapshot) -> str:
    """Return why a running backup is about to need what is being reclaimed."""
    del before
    if not facts.running_backup_bytes_needed:
        return ""
    if facts.running_backup_bytes_needed <= facts.free_bytes:
        return ""
    return (
        f"a backup is running and still needs about {facts.running_backup_bytes_needed} bytes, "
        f"and {facts.free_bytes} are free. Reclaiming into a datastore a running backup is "
        f"about to fill fails the backup and frees the space for nothing."
    )


def _not_deleting_a_backup_to_make_room(facts: Facts, before: StateSnapshot) -> str:
    """Return why deleting these items to make room for a backup is refused."""
    del before
    if not facts.making_room_for_a_backup:
        return ""
    backups = sorted(item.volume_id for item in facts.items if item.is_recovery_point)
    if not backups:
        return ""
    return (
        f"this would delete {', '.join(backups)} in order to make room for a backup. Trading a "
        f"recovery point that exists for one that does not yet is not a way to have more of "
        f"them, and it is the trade that leaves an estate with none."
    )


#: What every check is: a fact set and the approved state in, and either the
#: sentence that refuses or the empty string out.
type Check = Callable[[Facts, StateSnapshot], str]

#: One function per precondition, so ``evaluate`` is a loop rather than a chain
#: of branches and a precondition added without a check fails at import.
_CHECKS: Final[dict[Precondition, Check]] = {}


def _register() -> None:
    """Bind each precondition to its check, and refuse a precondition with none."""
    checks = {
        Precondition.TARGET_UNCHANGED: _target_unchanged,
        Precondition.HOLDING_TASK_DEAD: _holding_task_dead,
        Precondition.GUEST_UNLOCKED: _guest_unlocked,
        Precondition.CLUSTER_QUORATE: _cluster_quorate,
        Precondition.NODE_NOT_AMBIGUOUSLY_DEAD: _node_not_ambiguously_dead,
        Precondition.TARGET_NODE_SEES_STORAGE: _target_node_sees_storage,
        Precondition.ONLINE_MIGRATION_POSSIBLE: _online_migration_possible,
        Precondition.NO_SCHEDULED_BACKUP_COLLISION: _no_scheduled_backup_collision,
        Precondition.VOLUME_BELONGS_TO_NO_GUEST: _volume_belongs_to_no_guest,
        Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE: _no_running_backup_needs_the_space,
        Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM: _not_deleting_a_backup_to_make_room,
    }
    missing = [name.value for name in Precondition if name not in checks]
    if missing:
        raise ValueError(
            f"these preconditions have no check and would silently hold: {', '.join(missing)}"
        )
    _CHECKS.update(checks)


_register()


__all__ = [
    "Facts",
    "Precondition",
    "PreconditionRefused",
    "Refusal",
    "evaluate",
]
