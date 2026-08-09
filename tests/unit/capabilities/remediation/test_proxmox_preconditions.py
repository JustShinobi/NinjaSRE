"""The refusals, evaluated as pure functions of a reading taken right now.

Every one of these is a case where the correct behaviour is to stop. That makes
them the hardest part of the feature to be confident about from the code alone,
and the easiest part to be confident about from a test — the evaluation takes a
value and returns refusals, so a two-node split brain is a dictionary rather than
a cluster somebody has to break.

The refusals are asserted by *name and reason*, not only by count. "It refused"
and "it refused for the reason an operator can act on" are different properties,
and only the second is worth anything at four in the morning.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from capabilities.tools.remediation.proxmox import DECLARATIONS
from capabilities.tools.remediation.proxmox.preconditions import (
    Facts,
    Precondition,
    PreconditionRefused,
    Refusal,
    evaluate,
)
from capabilities.tools.remediation.proxmox.risk import ReclaimableItem
from config.constants.hypervisor import BACKUP_COLLISION_WINDOW_SECONDS
from integrations.proxmox.models import TaskRecord
from platform.remediation.models import StateSnapshot

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def approved(**values: object) -> StateSnapshot:
    """Return the state an approval was granted against."""
    return StateSnapshot(target="lxc/100@homelab", observed_at=EPOCH, values=dict(values))


def refusals_for(precondition: Precondition, facts: Facts, before: StateSnapshot) -> list[str]:
    """Return the reasons ``precondition`` gives for refusing, empty when it permits."""
    return [refusal.reason for refusal in evaluate((precondition,), facts=facts, before=before)]


# --- The target changed after the proposal ------------------------------------


def test_a_guest_that_migrated_after_the_proposal_causes_a_refusal() -> None:
    """The approval was given for the earlier state; this is a different action."""
    before = approved(node="pve02", lock="")
    facts = Facts(identity={"node": "pve01", "lock": ""})

    reasons = refusals_for(Precondition.TARGET_UNCHANGED, facts, before)

    assert reasons
    assert "node was 'pve02' and is now 'pve01'" in reasons[0]


def test_a_lock_taken_after_the_proposal_causes_a_refusal() -> None:
    """A guest a live operation has since claimed is not the guest that was approved."""
    before = approved(node="pve02", lock="")
    facts = Facts(identity={"node": "pve02", "lock": "backup"})

    reasons = refusals_for(Precondition.TARGET_UNCHANGED, facts, before)

    assert reasons
    assert "lock was '' and is now 'backup'" in reasons[0]


def test_an_unchanged_target_permits_the_action() -> None:
    """The other half, so the check cannot pass by refusing everything."""
    before = approved(node="pve02", lock="")
    facts = Facts(identity={"node": "pve02", "lock": ""})

    assert refusals_for(Precondition.TARGET_UNCHANGED, facts, before) == []


def test_a_target_that_could_not_be_read_is_a_refusal_rather_than_a_pass() -> None:
    """ "We could not tell" must not be collapsed into "nothing changed"."""
    reasons = refusals_for(
        Precondition.TARGET_UNCHANGED, Facts(identity=None), approved(node="pve02")
    )

    assert reasons
    assert "could not be read" in reasons[0]


def test_an_approval_granted_against_a_state_nobody_read_is_refused() -> None:
    """There is nothing to compare the current reading with, so there is no basis."""
    unread = StateSnapshot.unreadable("lxc/100@homelab", at=EPOCH)

    reasons = refusals_for(Precondition.TARGET_UNCHANGED, Facts(identity={"node": "a"}), unread)

    assert reasons
    assert "never read" in reasons[0]


# --- The lock and its holder --------------------------------------------------


def test_unlock_refuses_while_the_holding_task_is_alive() -> None:
    """Clearing a lock whose holder is running gives one guest two writers."""
    alive = TaskRecord(upid="UPID:pve02:1:1:1:vzdump:100:root@pam:", task_type="vzdump")
    facts = Facts(guest_lock="backup", holding_task=alive)

    reasons = refusals_for(Precondition.HOLDING_TASK_DEAD, facts, approved())

    assert reasons
    assert "still running" in reasons[0]


def test_unlock_refuses_when_no_task_can_be_found_holding_the_lock() -> None:
    """An unidentifiable holder is unknown, and unknown is not dead."""
    facts = Facts(guest_lock="backup", holding_task=None)

    reasons = refusals_for(Precondition.HOLDING_TASK_DEAD, facts, approved())

    assert reasons
    assert "unknown" in reasons[0]


def test_unlock_proceeds_once_the_holding_task_is_confirmed_finished() -> None:
    """The primary story: a backup died, its lock is orphaned, the guest is freed."""
    dead = TaskRecord(
        upid="UPID:pve02:1:1:1:vzdump:100:root@pam:",
        task_type="vzdump",
        status="stopped",
        exit_status="job errors",
        ended_at=1_754_802_400,
    )
    facts = Facts(guest_lock="backup", holding_task=dead)

    assert refusals_for(Precondition.HOLDING_TASK_DEAD, facts, approved()) == []


def test_every_other_guest_write_refuses_while_the_guest_is_locked() -> None:
    """Proxmox would refuse it too; refusing here says which lock and why."""
    reasons = refusals_for(Precondition.GUEST_UNLOCKED, Facts(guest_lock="migrate"), approved())

    assert reasons
    assert "'migrate'" in reasons[0]


# --- Quorum -------------------------------------------------------------------


def test_a_configuration_write_without_quorum_refuses_with_the_reason() -> None:
    """The configuration filesystem is read-only, so the write cannot land at all."""
    facts = Facts(quorate=False, is_clustered=True)

    reasons = refusals_for(Precondition.CLUSTER_QUORATE, facts, approved())

    assert reasons
    assert "read-only" in reasons[0]
    assert "quorum" in reasons[0]


def test_a_single_node_installation_is_not_treated_as_having_lost_quorum() -> None:
    """It never had one, and reporting it unquorate is a finding about nothing."""
    facts = Facts(quorate=False, is_clustered=False)

    assert refusals_for(Precondition.CLUSTER_QUORATE, facts, approved()) == []


# --- The two-node ambiguity ---------------------------------------------------


def test_a_two_node_cluster_with_a_silent_peer_refuses_the_dead_node_assumption() -> None:
    """Nothing here distinguishes a dead node from an unreachable one, and it says so."""
    facts = Facts(
        is_clustered=True,
        members=("pve01", "pve02"),
        online_nodes=("pve01",),
        contributing_quorum_device=False,
    )

    reasons = refusals_for(Precondition.NODE_NOT_AMBIGUOUSLY_DEAD, facts, approved())

    assert reasons
    assert "two-node cluster" in reasons[0]
    assert "dead from one that is merely unreachable" in reasons[0]
    assert "pve02" in reasons[0]


def test_a_three_node_cluster_votes_its_way_out_of_the_ambiguity() -> None:
    """The refusal is about undecidability, not about a node being down."""
    facts = Facts(
        is_clustered=True,
        members=("pve01", "pve02", "pve03"),
        online_nodes=("pve01", "pve02"),
    )

    assert refusals_for(Precondition.NODE_NOT_AMBIGUOUSLY_DEAD, facts, approved()) == []


def test_a_contributing_quorum_device_resolves_the_ambiguity() -> None:
    """A third vote is exactly what makes the question decidable."""
    facts = Facts(
        is_clustered=True,
        members=("pve01", "pve02"),
        online_nodes=("pve01",),
        contributing_quorum_device=True,
    )

    assert refusals_for(Precondition.NODE_NOT_AMBIGUOUSLY_DEAD, facts, approved()) == []


def test_a_two_node_cluster_with_both_members_answering_permits_the_action() -> None:
    """There is nothing to be wrong about while both are talking."""
    facts = Facts(
        is_clustered=True,
        members=("pve01", "pve02"),
        online_nodes=("pve01", "pve02"),
    )

    assert refusals_for(Precondition.NODE_NOT_AMBIGUOUSLY_DEAD, facts, approved()) == []


# --- Movement -----------------------------------------------------------------


def test_a_migration_into_a_node_without_the_guests_storage_is_refused() -> None:
    """Proxmox would accept it and fail at the far end, leaving the guest stopped."""
    facts = Facts(
        target_node="pve01",
        guest_datastores=("data-pool", "local-lvm"),
        target_node_datastores=("local-lvm",),
    )

    reasons = refusals_for(Precondition.TARGET_NODE_SEES_STORAGE, facts, approved())

    assert reasons
    assert "data-pool" in reasons[0]
    assert "local-lvm" not in reasons[0].split(",")[0]


def test_a_migration_with_no_receiving_node_named_is_refused() -> None:
    """Nothing could be checked against one, so nothing was."""
    reasons = refusals_for(Precondition.TARGET_NODE_SEES_STORAGE, Facts(), approved())

    assert reasons
    assert "no receiving node" in reasons[0]


def test_a_migration_refuses_rather_than_silently_going_offline() -> None:
    """An offline migration is a different action with a different cost."""
    facts = Facts(online_migration_blocker="it declares hostpci0, which is hardware in one machine")

    reasons = refusals_for(Precondition.ONLINE_MIGRATION_POSSIBLE, facts, approved())

    assert reasons
    assert "offline migration" in reasons[0]
    assert "hostpci0" in reasons[0]


# --- Backups ------------------------------------------------------------------


def test_a_backup_retry_refuses_to_collide_with_a_scheduled_run() -> None:
    """Two vzdump runs against one guest contend for the same lock and datastore."""
    facts = Facts(seconds_until_scheduled_backup=BACKUP_COLLISION_WINDOW_SECONDS - 1)

    reasons = refusals_for(Precondition.NO_SCHEDULED_BACKUP_COLLISION, facts, approved())

    assert reasons
    assert "collision window" in reasons[0]


def test_a_backup_retry_outside_the_window_proceeds() -> None:
    """The window is a bound, and a bound that refused everything would be a ban."""
    facts = Facts(seconds_until_scheduled_backup=BACKUP_COLLISION_WINDOW_SECONDS + 1)

    assert refusals_for(Precondition.NO_SCHEDULED_BACKUP_COLLISION, facts, approved()) == []


def test_a_guest_nothing_scheduled_covers_does_not_collide_with_anything() -> None:
    """A job that is switched off covers nothing, which is why absence is a real answer."""
    assert (
        refusals_for(
            Precondition.NO_SCHEDULED_BACKUP_COLLISION,
            Facts(seconds_until_scheduled_backup=None),
            approved(),
        )
        == []
    )


# --- Storage ------------------------------------------------------------------


def test_removing_a_volume_a_guest_still_references_is_refused_at_execution() -> None:
    """A guest created since the proposal is the volume nobody would re-check."""
    facts = Facts(
        items=(ReclaimableItem(volume_id="local-lvm:vm-129-disk-0", content="images"),),
        volume_owners={"local-lvm:vm-129-disk-0": 129},
    )

    reasons = refusals_for(Precondition.VOLUME_BELONGS_TO_NO_GUEST, facts, approved())

    assert reasons
    assert "belongs to guest 129" in reasons[0]
    assert "at execution rather than at proposal" in reasons[0]


def test_reclaiming_space_a_running_backup_is_about_to_need_is_refused() -> None:
    """Freeing space into a datastore a backup is about to fill fails the backup."""
    facts = Facts(running_backup_bytes_needed=40_000_000_000, free_bytes=1_000_000_000)

    reasons = refusals_for(Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE, facts, approved())

    assert reasons
    assert "a backup is running" in reasons[0]


def test_reclaiming_space_a_running_backup_already_has_room_for_proceeds() -> None:
    """The refusal is about the shortfall, not about a backup existing."""
    facts = Facts(running_backup_bytes_needed=1_000_000, free_bytes=40_000_000_000)

    assert refusals_for(Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE, facts, approved()) == []


def test_deleting_a_backup_in_order_to_make_room_for_a_backup_is_refused() -> None:
    """Trading a recovery point that exists for one that does not yet is not more of them."""
    facts = Facts(
        making_room_for_a_backup=True,
        items=(
            ReclaimableItem(volume_id="TeraChad:backup/vzdump-lxc-100.tar.zst", content="backup"),
        ),
    )

    reasons = refusals_for(Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM, facts, approved())

    assert reasons
    assert "vzdump-lxc-100" in reasons[0]


def test_deleting_a_plain_disk_image_to_make_room_for_a_backup_is_permitted() -> None:
    """The prohibition is about recovery points, not about deleting while a backup runs."""
    facts = Facts(
        making_room_for_a_backup=True,
        items=(ReclaimableItem(volume_id="local-lvm:vm-129-disk-0", content="images"),),
    )

    assert refusals_for(Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM, facts, approved()) == []


# --- The whole evaluation -----------------------------------------------------


def test_every_unmet_precondition_is_reported_rather_than_the_first() -> None:
    """An operator widening a proposal wants all of them, not one per attempt."""
    facts = Facts(quorate=False, guest_lock="backup", identity={"node": "pve01"})

    refused = evaluate(
        (Precondition.TARGET_UNCHANGED, Precondition.CLUSTER_QUORATE, Precondition.GUEST_UNLOCKED),
        facts=facts,
        before=approved(node="pve02"),
    )

    assert {refusal.precondition for refusal in refused} == {
        Precondition.TARGET_UNCHANGED,
        Precondition.CLUSTER_QUORATE,
        Precondition.GUEST_UNLOCKED,
    }


def test_the_refusal_names_every_precondition_and_reads_as_one_message() -> None:
    """A refusal nobody can read is a refusal somebody works around."""
    refused = PreconditionRefused(
        "proxmox_unlock_guest",
        "lxc/100@homelab",
        (Refusal(precondition=Precondition.HOLDING_TASK_DEAD, reason="the task is still running"),),
    )

    assert refused.names == ("holding_task_dead",)
    assert "proxmox_unlock_guest" in str(refused)
    assert "still running" in str(refused)


def test_every_precondition_has_a_check_and_a_description() -> None:
    """A precondition with no check would silently hold, which is the worst outcome."""
    for precondition in Precondition:
        assert precondition.describe().strip()
        assert evaluate((precondition,), facts=Facts(), before=approved()) is not None


def test_every_configuration_writing_capability_declares_the_quorum_precondition() -> None:
    """Swept over the registry, because the fourteenth write will need it too."""
    for name, declared in DECLARATIONS.items():
        if not declared.writes_configuration:
            continue
        assert Precondition.CLUSTER_QUORATE in declared.preconditions, name


def test_every_capability_that_would_assume_a_node_is_dead_declares_the_ambiguity_check() -> None:
    """The refusal has to be attached to the actions that would need it, not to a list."""
    for name, declared in DECLARATIONS.items():
        if not declared.assumes_node_is_dead:
            continue
        assert Precondition.NODE_NOT_AMBIGUOUSLY_DEAD in declared.preconditions, name


def test_every_capability_re_reads_its_target_before_acting() -> None:
    """An investigation that took four minutes has a four-minute-old picture."""
    for name, declared in DECLARATIONS.items():
        assert Precondition.TARGET_UNCHANGED in declared.preconditions, name
