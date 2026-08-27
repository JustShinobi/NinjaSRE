"""Phase 3: the guest, once the cluster and the storage beneath it are ruled out.

Every distinction here is a pair of readings that look alike and have completely
different remedies, which is why the tool makes the distinction rather than
leaving it to whoever reads the output.

**A live lock and an orphaned one.** Both present as ``lock: backup`` and a guest
that will not start. One is a backup genuinely in progress and clearing it
corrupts the backup; the other is a lock left by a task that died and clearing it
is the fix. The difference is whether the task is still running, which the guest
record does not say.

**Host storage full and guest filesystem full.** The guest reports write errors
in both cases. One is fixed on the hypervisor and one inside the guest, and
starting with the wrong one costs the whole first pass.

**Host memory pressure and guest memory pressure.** The same again: a node that
is swapping and a guest that is out of memory produce similar-looking guests and
opposite remedies.

**A guest that cannot move and a guest that should not.** Local disks, a
passthrough device that exists on one node only, and a cluster without quorum all
prevent a migration, and each of them is a different conversation.
"""

from __future__ import annotations

import pytest

from integrations.proxmox.client import _task
from integrations.proxmox.tools.guest_pressure import proxmox_guest_pressure
from integrations.proxmox.tools.guest_start_diagnosis import proxmox_guest_start_diagnosis
from integrations.proxmox.tools.guest_tasks import proxmox_guest_tasks
from integrations.proxmox.tools.migration_feasibility import proxmox_migration_feasibility
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, investigating

pytestmark = pytest.mark.unit

#: A vzdump that is still running, for the guest whose lock says ``backup``. The
#: same lock as the orphaned case and the opposite correct action.
_RUNNING_BACKUP = {
    "upid": "UPID:pve01:0000C9F0:05130000:68943C00:vzdump:9000:root@pam:",
    "type": "vzdump",
    "status": "running",
    "starttime": 1_754_802_900,
    "node": PRIMARY,
    "user": "root@pam",
}


_FAILED_START = {
    "upid": "UPID:pve01:0000C201:05120000:68943B00:qmstart:9000:root@pam:",
    "type": "qmstart",
    "status": "storage 'externo-nfs-pve01' is not online",
    "starttime": 1_754_802_500,
    "endtime": 1_754_802_501,
    "node": PRIMARY,
    "user": "root@pam",
}


# --- Start diagnosis ----------------------------------------------------------


async def test_a_lock_left_by_a_task_that_died_is_reported_as_orphaned_and_named() -> None:
    with investigating():
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    lock = result.value["lock"]
    assert lock["held"]
    assert lock["kind"] == "backup"
    assert lock["orphaned"]
    assert "vzdump" in lock["task"]
    assert lock["task_age_seconds"] > 0


async def test_a_lock_held_by_a_task_that_is_still_running_is_not_reported_as_orphaned() -> None:
    """Clearing this one corrupts a backup that is in progress."""
    with investigating(responses={f"/nodes/{PRIMARY}/tasks": [_RUNNING_BACKUP]}):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    lock = result.value["lock"]
    assert lock["held"]
    assert not lock["orphaned"]
    assert "still running" in lock["verdict"].lower()


async def test_the_guests_last_task_error_is_carried_in_the_vendors_own_words() -> None:
    """The failed start is in the node's task log, which is where the guest's history is."""
    with investigating(responses={f"/nodes/{PRIMARY}/tasks": [_FAILED_START]}):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    failures = result.value["recent_failures"]
    assert failures
    assert "externo-nfs-pve01" in failures[0]["error"]


async def test_a_datastore_the_guests_disk_needs_and_the_node_cannot_reach_is_a_cause() -> None:
    with investigating():
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    reasons = " ".join(result.value["candidate_causes"])
    assert "externo-nfs-pve01" in reasons or "storage" in reasons.lower()


async def test_a_passthrough_device_absent_on_this_node_is_reported_as_a_cause() -> None:
    with investigating(
        responses={
            f"/nodes/{PRIMARY}/qemu/9000/config": {
                "name": "windows-lab",
                "cores": 4,
                "memory": 8192,
                "ostype": "win11",
                "hostpci0": "0000:01:00,pcie=1",
                "scsi0": "local-lvm:vm-9000-disk-0,size=128G",
            }
        }
    ):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    assert result.value["passthrough_devices"] == ["hostpci0"]
    assert any("passthrough" in reason.lower() for reason in result.value["candidate_causes"])


async def test_a_cluster_without_quorum_makes_every_other_cause_downstream() -> None:
    """The most likely cause is stated, and without quorum it is never the guest."""
    with investigating(ClusterState.NO_QUORUM):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    assert "quorum" in result.value["most_likely_cause"].lower()


async def test_the_node_having_no_memory_left_for_the_guest_is_reported() -> None:
    with investigating(
        responses={
            f"/nodes/{PRIMARY}/status": {
                "uptime": 813_600,
                "loadavg": ["1.42", "1.31", "1.20"],
                "cpu": 0.63,
                "cpuinfo": {"cpus": 8},
                "memory": {"total": 33_284_000_000, "used": 32_900_000_000},
                "swap": {"total": 8_589_934_592, "used": 6_000_000_000},
                "rootfs": {"total": 103_079_215_104, "used": 34_016_000_000},
                "kversion": "Linux 7.0.14-8-pve",
                "pveversion": "pve-manager/9.2.6",
            }
        }
    ):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    assert not result.value["node_resources"]["memory_available_for_guest"]
    assert any("memory" in reason.lower() for reason in result.value["candidate_causes"])


# --- Pressure -----------------------------------------------------------------


async def test_host_storage_full_and_a_guest_filesystem_that_is_not_is_attributed_to_the_host() -> (
    None
):
    with investigating(
        responses={
            f"/nodes/{PRIMARY}/storage": [
                {
                    "storage": "local-lvm",
                    "type": "lvmthin",
                    "active": 1,
                    "enabled": 1,
                    "shared": 0,
                    "total": 375_700_000_000,
                    "used": 375_000_000_000,
                    "content": "images,rootdir",
                }
            ]
        }
    ):
        result = await proxmox_guest_pressure(PRIMARY, 9000, kind="qemu")

    storage = result.value["storage"]
    assert storage["attribution"] == "host"
    assert "host" in result.evidence[0].summary.lower()
    assert storage["guest_filesystems"], "the guest agent answered and was not reported"


async def test_a_guest_whose_own_filesystem_is_full_on_a_host_that_is_not_is_attributed_to_it() -> (
    None
):
    with investigating(
        responses={
            f"/nodes/{PRIMARY}/qemu/9000/agent/get-fsinfo": {
                "result": [
                    {
                        "mountpoint": "C:\\",
                        "total-bytes": 137_438_953_472,
                        "used-bytes": 136_000_000_000,
                    }
                ]
            }
        }
    ):
        result = await proxmox_guest_pressure(PRIMARY, 9000, kind="qemu")

    assert result.value["storage"]["attribution"] == "guest"


async def test_an_agent_that_does_not_answer_is_not_reported_as_an_unhealthy_guest() -> None:
    with investigating():
        result = await proxmox_guest_pressure(SECONDARY, 100, kind="lxc")

    assert result.value["storage"]["attribution"] == "undetermined"
    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert "agent" in questions.lower()


async def test_host_memory_pressure_is_told_apart_from_guest_memory_pressure() -> None:
    with investigating(
        responses={
            f"/nodes/{SECONDARY}/status": {
                "uptime": 813_600,
                "loadavg": ["9.10", "8.20", "7.90"],
                "cpu": 0.94,
                "cpuinfo": {"cpus": 12},
                "memory": {"total": 67_355_000_000, "used": 66_800_000_000},
                "swap": {"total": 8_589_934_592, "used": 7_900_000_000},
                "rootfs": {"total": 103_079_215_104, "used": 82_463_000_000},
                "kversion": "Linux 7.0.14-8-pve",
                "pveversion": "pve-manager/9.2.6",
            }
        }
    ):
        result = await proxmox_guest_pressure(SECONDARY, 140, kind="lxc")

    memory = result.value["memory"]
    assert memory["host_under_pressure"]
    assert not memory["guest_under_pressure"]
    assert memory["attribution"] == "host"
    assert memory["host_swap_ratio"] > 0.5


async def test_a_guest_at_its_own_memory_ceiling_on_a_comfortable_host_is_attributed_to_it() -> (
    None
):
    with investigating():
        result = await proxmox_guest_pressure(SECONDARY, 115, kind="lxc")

    memory = result.value["memory"]
    assert memory["guest_under_pressure"]
    assert memory["attribution"] == "guest"


async def test_ballooning_and_cpu_steal_are_named_rather_than_silently_omitted() -> None:
    with investigating():
        result = await proxmox_guest_pressure(PRIMARY, 9000, kind="qemu")

    assert "ballooning" in result.value
    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert "steal" in questions.lower()


# --- Task history -------------------------------------------------------------


async def test_a_guests_recent_tasks_are_returned_with_the_vendors_error_text() -> None:
    """The node's task log is where a guest's own history is, so that is what is read."""
    with investigating(responses={f"/nodes/{PRIMARY}/tasks": [_FAILED_START]}):
        result = await proxmox_guest_tasks(PRIMARY, 9000, kind="qemu")

    assert result.value["failures"]
    assert result.value["failures"][0]["type"] == "qmstart"
    assert "not online" in result.value["failures"][0]["error"]


async def test_a_guest_with_no_task_history_says_so_rather_than_returning_nothing() -> None:
    """Nothing has been done to it through the API, which is a finding of its own."""
    with investigating():
        result = await proxmox_guest_tasks(SECONDARY, 140, kind="lxc")

    assert result.value["tasks"] == []
    assert "no task" in result.evidence[0].summary.lower()


# --- Migration ----------------------------------------------------------------


async def test_a_guest_on_node_local_storage_cannot_migrate_and_the_disk_is_named() -> None:
    with investigating():
        result = await proxmox_migration_feasibility(SECONDARY, 100, kind="lxc")

    assert not result.value["can_migrate"]
    blockers = " ".join(blocker["reason"] for blocker in result.value["blockers"])
    assert "data-pool" in blockers


async def test_a_passthrough_device_blocks_migration_and_is_reported_separately() -> None:
    with investigating(
        responses={
            f"/nodes/{PRIMARY}/qemu/9000/config": {
                "name": "windows-lab",
                "cores": 4,
                "memory": 8192,
                "hostpci0": "0000:01:00,pcie=1",
                "scsi0": "local-lvm:vm-9000-disk-0,size=128G",
            }
        }
    ):
        result = await proxmox_migration_feasibility(PRIMARY, 9000, kind="qemu")

    kinds = {blocker["kind"] for blocker in result.value["blockers"]}
    assert "passthrough" in kinds


async def test_a_cluster_without_quorum_blocks_every_migration_whatever_the_guest_is() -> None:
    with investigating(ClusterState.NO_QUORUM):
        result = await proxmox_migration_feasibility(SECONDARY, 100, kind="lxc")

    kinds = {blocker["kind"] for blocker in result.value["blockers"]}
    assert "quorum" in kinds
    assert not result.value["can_migrate"]


async def test_the_targets_that_could_take_the_guest_are_reported_by_name() -> None:
    with investigating():
        result = await proxmox_migration_feasibility(SECONDARY, 100, kind="lxc")

    targets = {entry["node"]: entry for entry in result.value["targets"]}
    assert PRIMARY in targets
    assert not targets[PRIMARY]["can_receive"]
    assert targets[PRIMARY]["reasons"]


class TestATaskThatIsNotAboutAGuest:
    """A node's task log is not a guest's, and Proxmox says so in the id field.

    ``UPID:node:pid:pstart:starttime:type:id:user:`` packs an ``id`` whose
    meaning follows the task type. For a guest operation it is the vmid. For a
    backup it is the storage. For anything about the node itself it is the node
    name. `_task` read all three as ``int(...)``, so a single ``vzdump`` or
    ``srvstop`` entry anywhere in the log raised ``ValueError`` and took the
    whole call down with it.

    That is worse than losing one row, and worse than it looks. Three
    capabilities read this log — the guest's task history, backup coverage and
    backup failures — so on a cluster that takes backups, all three fail
    together and permanently. It is the failure that stopped a real
    investigation from ever learning that a container had been shut down by
    hand: the evidence was three rows further down a list that never parsed.

    Compounding it, ``ValueError`` classifies as ``invalid_arguments``, so the
    model is told the arguments it sent were wrong. They were not, and it
    retries with different ones.
    """

    def test_a_task_whose_id_names_a_node_does_not_take_the_log_with_it(self) -> None:
        record = _task(
            {
                "upid": "UPID:pve01:0000ABCD:00000000:68943A10:srvstop:pve01:root@pam:",
                "type": "srvstop",
                "status": "OK",
                "id": "pve01",
            }
        )

        assert record.vmid == 0, "a task about the node is not a task about guest 0"
        assert record.task_type == "srvstop"
        assert record.node == "pve01"

    def test_a_backup_task_keyed_by_its_datastore_is_read_the_same_way(self) -> None:
        record = _task(
            {
                "upid": "UPID:pve02:0000BEEF:00000000:68943A10:vzdump:local-lvm:root@pam:",
                "type": "vzdump",
                "id": "local-lvm",
            }
        )

        assert record.vmid == 0

    def test_a_guest_task_still_carries_its_guest(self) -> None:
        """The whole point of the field, which the repair must not cost."""
        record = _task(
            {
                "upid": "UPID:pve01:0000ABCD:00000000:68943A10:vzshutdown:122:root@pam:",
                "type": "vzshutdown",
                "id": "122",
            }
        )

        assert record.vmid == 122
