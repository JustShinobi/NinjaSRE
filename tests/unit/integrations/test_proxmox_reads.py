"""Phases 2 to 6: everything this integration reads, against a recorded cluster.

No live hypervisor appears anywhere in this file, which is NFR-004. The corpus
in ``tests/support/proxmox.py`` was recorded from a two-node cluster in five
states, and the states are the point: a client tested only against a healthy
cluster is a client whose behaviour during the incident is unknown.

The readings worth naming, because each one exists because a datastore-level
threshold could not see it:

- **Quorum is a fact, not an error.** A cluster answering ``quorate: 0`` still
  answers most reads. Treating it as a connection failure would hide the single
  most important thing about a two-node cluster.
- **A thin pool has two percentages.** Data and metadata. A pool whose metadata
  is exhausted stops accepting writes while its data figure still looks fine.
- **A guest's volume is not its datastore.** ``local-lvm`` at 84% while the plex
  container sits at 99.6% of its own volume is the case that motivated this.
- **An absent guest agent is not an unhealthy guest.** Those are different
  sentences and only one of them is about the guest.
- **A node that is down still has guests.** They are stale, not gone.
"""

from __future__ import annotations

import pytest

from integrations.proxmox.client import MAX_TASK_LOG_LINES, ProxmoxClient
from tests.support.proxmox import (
    PRIMARY,
    SECONDARY,
    ZFS_POOL_DETAIL,
    ZFS_POOLS,
    ClusterState,
    client_for,
)

pytestmark = pytest.mark.unit


# --- Phase 2: the cluster -----------------------------------------------------


async def test_cluster_status_carries_quorum_votes_and_membership() -> None:
    client, _ = client_for()

    status = await client.cluster_status()

    assert status.name == "HAL9000"
    assert status.quorate
    assert status.expected_votes == 2
    assert status.total_votes == 2
    assert {member.name for member in status.members} == {PRIMARY, SECONDARY}
    assert all(member.online for member in status.members)


async def test_the_margin_a_two_node_cluster_has_is_reported_rather_than_inferred() -> None:
    """Two votes with a quorum of two is a margin of zero, which is the finding."""
    client, _ = client_for()

    status = await client.cluster_status()

    assert status.quorum_margin == 0


async def test_a_cluster_without_quorum_is_a_fact_and_not_a_failure() -> None:
    """T-011. The read succeeds and reports the condition."""
    client, _ = client_for(ClusterState.NO_QUORUM)

    status = await client.cluster_status()

    assert not status.quorate
    assert status.total_votes == 1
    assert status.quorum_margin < 0


async def test_a_read_that_needs_a_writable_cluster_filesystem_says_why_it_failed() -> None:
    """The other half of T-011: what does not work reports why, by name."""
    client, _ = client_for(ClusterState.NO_QUORUM)

    reading = await client.node_status("pve03-that-does-not-exist")

    assert not reading.available
    assert "pve03-that-does-not-exist" in reading.unavailable_reason


async def test_a_standalone_installation_with_no_cluster_still_reads() -> None:
    client, _ = client_for(ClusterState.SINGLE_NODE)

    status = await client.cluster_status()

    assert not status.is_clustered
    assert [member.name for member in status.members] == [PRIMARY]
    assert status.quorate, "a single node that is up is not a cluster that lost quorum"


async def test_the_cluster_resource_list_is_one_call_for_the_whole_estate() -> None:
    client, transport = client_for()

    resources = await client.cluster_resources()

    kinds = {record.get("type") for record in resources}
    assert {"node", "lxc", "qemu", "storage"} <= kinds
    assert transport.seen == ["/cluster/resources"]


async def test_corosync_configuration_and_the_cluster_log_are_readable() -> None:
    client, _ = client_for()

    config = await client.cluster_configuration()
    log = await client.cluster_log(limit=10)

    assert config.cluster_name == "HAL9000"
    assert config.transport == "knet"
    assert [node["node"] for node in config.nodes] == [PRIMARY, SECONDARY]
    assert log[0]["tag"] == "corosync"


async def test_a_corosync_configuration_with_no_two_node_setting_says_so() -> None:
    """A missing setting is a reading, and reporting it absent is the point."""
    client, _ = client_for()

    config = await client.cluster_configuration()

    assert not config.two_node
    assert not config.wait_for_all


async def test_high_availability_state_covers_resources_groups_manager_and_fencing() -> None:
    client, _ = client_for()

    state = await client.high_availability()

    assert [resource["sid"] for resource in state.resources] == ["ct:115"]
    assert state.groups == ()
    assert state.manager_node == PRIMARY
    assert state.fencing_mode


async def test_cluster_backup_jobs_carry_whether_they_are_enabled() -> None:
    """A job that exists and is disabled is the most dangerous shape a backup has."""
    client, _ = client_for()

    jobs = await client.backup_jobs()

    by_id = {job.job_id: job for job in jobs}
    assert not by_id["backup-7d831311"].enabled
    assert by_id["backup-7d831311"].covers_everything
    assert by_id["backup-33b5e58a"].enabled
    assert by_id["backup-33b5e58a"].vmids == (100, 115, 140, 142, 161)


# --- Phase 3: nodes -----------------------------------------------------------


async def test_node_status_reads_load_memory_root_filesystem_and_versions() -> None:
    client, _ = client_for()

    reading = await client.node_status(SECONDARY)

    assert reading.available
    node = reading.require()
    assert node.uptime_seconds == 813_600
    assert node.load_average == pytest.approx(0.31)
    assert node.cpu_ratio == pytest.approx(0.09)
    assert node.root_filesystem_ratio == pytest.approx(0.80, abs=0.01)
    assert node.kernel_version == "Linux 7.0.14-8-pve"
    assert node.proxmox_version == "9.2.6"


async def test_a_node_that_is_down_reports_unavailable_rather_than_raising() -> None:
    client, _ = client_for(ClusterState.NODE_DOWN)

    reading = await client.node_status(SECONDARY)

    assert not reading.available
    assert "595" in reading.unavailable_reason


async def test_storage_list_and_per_datastore_status_are_readable() -> None:
    client, _ = client_for()

    stores = await client.node_storage(SECONDARY)
    status = await client.datastore_status(SECONDARY, "local-lvm")

    assert {store.name for store in stores} == {"local-lvm", "TeraChad"}
    assert next(store for store in stores if store.name == "TeraChad").shared
    assert status.available
    assert status.require().used_ratio == pytest.approx(0.844, abs=0.005)


async def test_physical_disks_carry_their_smart_verdict() -> None:
    client, _ = client_for()

    disks = await client.node_disks(SECONDARY)

    assert {disk.device for disk in disks} == {"/dev/nvme0n1", "/dev/sda"}
    assert all(disk.smart_passed for disk in disks)
    assert next(disk for disk in disks if disk.device == "/dev/nvme0n1").serial


async def test_a_failing_disk_is_reported_as_failing() -> None:
    client, _ = client_for(ClusterState.DEGRADED)

    disks = await client.node_disks(SECONDARY)

    assert not next(disk for disk in disks if disk.device == "/dev/sda").smart_passed


async def test_thin_pool_data_and_metadata_are_separate_readings() -> None:
    """FR-013a. A pool out of metadata stops writing while its data looks fine."""
    client, _ = client_for()

    pools = await client.thin_pools(SECONDARY)

    data_pool = next(pool for pool in pools if pool.name == "data-pool")
    assert data_pool.data_percent == pytest.approx(72.38)
    assert data_pool.metadata_percent == pytest.approx(31.98)
    assert not data_pool.metadata_critical


async def test_a_thin_pool_out_of_metadata_is_critical_while_its_data_is_not() -> None:
    client, _ = client_for(ClusterState.DEGRADED)

    pools = await client.thin_pools(SECONDARY)

    pool = next(pool for pool in pools if pool.name == "data")
    assert pool.metadata_critical
    assert pool.data_percent < 90


async def test_a_node_with_no_zfs_is_the_ordinary_case_and_not_a_failure() -> None:
    """FR-013b. Neither reference node has a pool, and that is not an error."""
    client, _ = client_for()

    reading = await client.zfs_pools(SECONDARY)

    assert reading.available
    assert reading.require() == ()


async def test_node_tasks_and_one_tasks_status_and_log_are_readable() -> None:
    client, _ = client_for()

    tasks = await client.node_tasks(SECONDARY, limit=10)

    assert len(tasks) == 2
    assert tasks[0].succeeded
    assert not tasks[1].succeeded
    assert tasks[1].upid.startswith("UPID:pve02:")


async def test_replication_jobs_are_read_and_none_is_a_finding_not_an_error() -> None:
    """No replication with node-local storage is the reference cluster's state."""
    client, _ = client_for()

    jobs = await client.replication_jobs(SECONDARY)

    assert jobs == ()


async def test_certificate_expiry_and_pending_updates_are_readable() -> None:
    client, _ = client_for()

    certificates = await client.node_certificates(SECONDARY)
    updates = await client.pending_updates(SECONDARY)

    assert certificates[0]["filename"] == "pveproxy-ssl.pem"
    assert {update.package for update in updates} == {"proxmox-kernel-7.0", "jq"}
    assert next(update for update in updates if update.package == "jq").is_security


async def test_a_kernel_upgrade_pending_is_visible_in_the_update_list() -> None:
    """The precondition of the reference cluster's only total outage."""
    client, _ = client_for()

    updates = await client.pending_updates(SECONDARY)

    assert any(update.is_kernel for update in updates)


async def test_network_interfaces_and_time_synchronisation_are_readable() -> None:
    client, _ = client_for()

    interfaces = await client.node_network(SECONDARY)
    clock = await client.node_time(SECONDARY)

    bridges = [interface for interface in interfaces if interface.is_bridge]
    assert [bridge.name for bridge in bridges] == ["vmbr0"]
    assert bridges[0].active
    assert clock["timezone"] == "Europe/Lisbon"


# --- Phase 4: guests ----------------------------------------------------------


async def test_a_container_and_a_virtual_machine_are_distinct_kinds() -> None:
    """FR-021. Different endpoints, different configuration, different failures."""
    client, transport = client_for()

    container = await client.guest_status(SECONDARY, 100, kind="lxc")
    machine = await client.guest_status(PRIMARY, 9000, kind="qemu")

    assert container.kind == "lxc"
    assert machine.kind == "qemu"
    assert "/lxc/100/" in transport.seen[0]
    assert "/qemu/9000/" in transport.seen[1]


async def test_an_unknown_guest_kind_is_refused_rather_than_guessed() -> None:
    client, _ = client_for()

    with pytest.raises(ValueError, match="lxc"):
        await client.guest_status(SECONDARY, 100, kind="container")


async def test_guest_status_carries_lock_state_and_high_availability_membership() -> None:
    client, _ = client_for()

    machine = await client.guest_status(PRIMARY, 9000, kind="qemu")

    assert machine.lock == "backup"
    assert machine.ha_managed
    assert machine.status == "stopped"


async def test_a_guest_with_no_name_set_is_read_without_inventing_one() -> None:
    """Proxmox omits the key; a client that filled it in would fabricate an identity."""
    client, _ = client_for()

    resources = await client.cluster_resources()

    nameless = next(record for record in resources if record.get("vmid") == 137)
    assert "name" not in nameless


async def test_guest_configuration_snapshots_and_pending_changes_are_readable() -> None:
    client, _ = client_for()

    config = await client.guest_configuration(SECONDARY, 100, kind="lxc")
    snapshots = await client.guest_snapshots(SECONDARY, 100, kind="lxc")
    pending = await client.guest_pending(SECONDARY, 100, kind="lxc")

    assert config["cores"] == 4
    assert [snapshot["name"] for snapshot in snapshots] == ["current", "before-upgrade"]
    assert pending[0]["key"] == "memory"


async def test_a_guest_agent_that_answers_is_distinguishable_from_one_that_does_not() -> None:
    """FR-020. An absent agent is not an unhealthy guest."""
    client, _ = client_for()

    answered = await client.guest_agent_filesystems(PRIMARY, 9000)
    absent = await client.guest_agent_filesystems(SECONDARY, 100)

    assert answered.available
    assert answered.require()[0]["mountpoint"] == "C:\\"
    assert not absent.available
    assert "agent" in absent.unavailable_reason.lower()


async def test_a_guests_own_task_history_is_readable() -> None:
    client, _ = client_for()

    tasks = await client.guest_tasks(SECONDARY, 100, kind="lxc")

    assert tasks == ()


# --- Phase 5: backups ---------------------------------------------------------


async def test_backup_task_outcomes_are_read_from_the_task_history() -> None:
    client, _ = client_for()

    outcomes = await client.backup_outcomes(SECONDARY)

    assert len(outcomes) == 2
    assert outcomes[0].vmid == 100
    assert outcomes[0].succeeded
    assert not outcomes[1].succeeded


async def test_the_most_recent_successful_backup_per_guest_is_answerable() -> None:
    client, _ = client_for()

    latest = await client.last_successful_backup(SECONDARY)

    assert latest[100].succeeded
    assert 129 not in latest, "a job that only ever failed has no successful backup"


async def test_retained_backup_contents_per_datastore_are_readable() -> None:
    client, _ = client_for()

    contents = await client.datastore_contents(SECONDARY, "local-lvm")

    assert contents[0]["volid"] == "local-lvm:vm-100-disk-0"


# --- Phase 6: tasks -----------------------------------------------------------


async def test_a_task_identifier_is_retained_and_its_status_is_pollable() -> None:
    client, transport = client_for()
    upid = "UPID:pve02:0000B1C4:0511D6A2:68943A10:vzdump:100:root@pam:"
    transport.cluster.responses[f"/nodes/{SECONDARY}/tasks/{upid}/status"] = {
        "status": "stopped",
        "exitstatus": "OK",
        "upid": upid,
    }

    task = await client.task_status(SECONDARY, upid)

    assert task.upid == upid
    assert task.finished
    assert task.succeeded


async def test_polling_stops_and_reports_a_task_still_running() -> None:
    """T-027. Bounded in calls, and honest about what it found."""
    client, transport = client_for()
    upid = "UPID:pve02:0000B1C4:0511D6A2:68943A10:vzdump:100:root@pam:"
    transport.cluster.responses[f"/nodes/{SECONDARY}/tasks/{upid}/status"] = {
        "status": "running",
        "upid": upid,
    }

    task = await client.await_task(SECONDARY, upid, max_polls=3, delay_seconds=0)

    assert not task.finished
    assert task.polls == 3
    assert "still running" in task.summary


async def test_polling_stops_as_soon_as_the_task_finishes() -> None:
    client, transport = client_for()
    upid = "UPID:pve02:0000B1C4:0511D6A2:68943A10:vzdump:100:root@pam:"
    transport.cluster.responses[f"/nodes/{SECONDARY}/tasks/{upid}/status"] = {
        "status": "stopped",
        "exitstatus": "OK",
        "upid": upid,
    }

    task = await client.await_task(SECONDARY, upid, max_polls=5, delay_seconds=0)

    assert task.finished
    assert task.polls == 1


async def test_a_task_log_that_grows_without_bound_is_read_boundedly() -> None:
    """T-028. A restore of a 900 GiB volume logs more than anything should hold."""
    client, transport = client_for()
    upid = "UPID:pve02:0000B1C4:0511D6A2:68943A10:vzdump:129:root@pam:"
    transport.cluster.responses[f"/nodes/{SECONDARY}/tasks/{upid}/log"] = [
        {"n": index, "t": f"line {index}"} for index in range(10_000)
    ]

    lines = await client.task_log(SECONDARY, upid)

    assert len(lines) == MAX_TASK_LOG_LINES


async def test_the_cheapest_authenticated_call_is_the_version_endpoint() -> None:
    """What verification and the health ledger both use to prove a token works."""
    client, transport = client_for()

    response = await client.ping()
    version = await client.version()

    assert response.status_code == 200
    assert version["version"] == "9.2.6"
    assert transport.seen == ["/version", "/version"]


async def test_a_raw_read_returns_the_answer_without_interpreting_the_envelope() -> None:
    """What a permission probe wants: was the call permitted, not what came back."""
    client, _ = client_for()

    response = await client.read_response("/cluster/status")

    assert response.status_code == 200
    assert b"HAL9000" in response.body


async def test_the_tokens_effective_privileges_are_readable() -> None:
    """Proxmox can be asked, which is unusual and is why verification names a gap."""
    client, _ = client_for()

    permissions = await client.access_permissions()

    assert permissions["/"]["Sys.Audit"] == 1
    assert permissions["/vms"]["VM.Audit"] == 1


async def test_each_guests_own_thin_volume_fill_is_read_separately_from_its_datastore() -> None:
    """FR-013a's second half: the reading a datastore threshold cannot make."""
    client, transport = client_for()
    transport.cluster.responses[f"/nodes/{SECONDARY}/disks/lvm"] = [
        {
            "lv": "vm-100-disk-0",
            "vg": "data-pool",
            "lv_size": 107_374_182_400,
            "data_percent": 99.60,
        },
        {"lv": "vm-9000-disk-0", "vg": "pve", "lv_size": 137_438_953_472, "data_percent": 41.20},
    ]

    volumes = await client.thin_volumes(SECONDARY)

    near_full = [volume for volume in volumes if volume.near_full]
    assert [volume.vmid for volume in near_full] == [100]
    assert near_full[0].data_percent == pytest.approx(99.60)


# --- The three reads an investigation needs and a survey did not -------------


async def test_the_cluster_wide_datastore_definitions_say_which_nodes_may_see_each() -> None:
    """A guest cannot move to a node its disk's datastore is not declared on."""
    client, _ = client_for()

    declared = await client.storage_configuration()

    by_name = {row["storage"]: row for row in declared}
    assert by_name["local-lvm"]["nodes"] == "", "an empty restriction means every node"
    assert by_name["TeraChad"]["nodes"] == SECONDARY


async def test_one_disks_smart_attributes_are_readable_per_device() -> None:
    """The health verdict is a summary; the attributes are what predicts."""
    client, _ = client_for()

    reading = await client.disk_smart(SECONDARY, "/dev/sda")

    assert reading.available
    attributes = {row["name"]: row for row in reading.require()["attributes"]}
    assert attributes["Current_Pending_Sector"]["raw"] == "24"


async def test_two_disks_on_one_node_report_their_own_attributes_and_not_each_others() -> None:
    client, _ = client_for()

    solid_state = await client.disk_smart(SECONDARY, "/dev/nvme0n1")
    spinning = await client.disk_smart(SECONDARY, "/dev/sda")

    assert solid_state.require()["type"] == "text"
    assert spinning.require()["type"] == "ata"


async def test_one_zfs_pools_devices_scrub_and_errors_are_readable() -> None:
    """A pool's health is a word; its device tree is where the fault is."""
    client, _ = client_for(
        responses={
            f"/nodes/{SECONDARY}/disks/zfs": list(ZFS_POOLS),
            f"/nodes/{SECONDARY}/disks/zfs/tank": ZFS_POOL_DETAIL,
        }
    )

    reading = await client.zfs_pool_detail(SECONDARY, "tank")

    assert reading.available
    detail = reading.require()
    assert detail["state"] == "ONLINE"
    assert "scrub repaired" in detail["scan"]


async def test_a_node_with_no_such_zfs_pool_reports_an_absent_reading() -> None:
    """Absent rather than empty: nothing looked, which is not the same as nothing wrong."""
    client, _ = client_for()

    reading = await client.zfs_pool_detail(SECONDARY, "tank")

    assert not reading.available
    assert "tank" in reading.unavailable_reason


# --- Failover, across the whole read surface ----------------------------------


async def test_every_read_reaches_the_cluster_through_a_surviving_node() -> None:
    """SC-007, at the client rather than at the ring."""
    client, transport = client_for(offline=frozenset({"pve01.acme.example"}))

    status = await client.cluster_status()

    assert status.name == "HAL9000"
    assert transport.hosts == ["pve01.acme.example", "pve02.acme.example"]


async def test_no_read_method_sends_anything_other_than_a_get() -> None:
    """NFR-002, structurally: a read that posted would be a read with an effect."""
    import inspect

    source = inspect.getsource(ProxmoxClient)

    for verb in ("self.post(", "self.put(", "self.delete("):
        assert verb not in source


async def test_high_availability_survives_a_cluster_that_retired_ha_groups() -> None:
    """Proxmox VE 9 migrates HA groups to HA rules and soft-disables the old
    endpoint: it answers 500 with "ha groups have been migrated to rules"
    rather than disappearing, because a part-upgraded cluster still has groups.

    Reading HA is one call among several in a sweep. A retired endpoint taking
    the whole read down means a deployment on the current Proxmox cannot
    discover its own estate — which is what happened.
    """
    from platform.credentials.proxy.model import OutboundResponse

    retired = OutboundResponse(
        500,
        {},
        b'{"data":null,"message":"cannot index groups: ha groups have been migrated to rules"}',
    )
    client, _ = client_for(
        responses={
            "/cluster/ha/groups": retired,
            "/cluster/ha/rules": [
                {"rule": "node-affinity-1", "type": "node-affinity", "resources": "ct:115"}
            ],
        }
    )

    state = await client.high_availability()

    assert [resource["sid"] for resource in state.resources] == ["ct:115"]
    assert [row["rule"] for row in state.groups] == ["node-affinity-1"]
    assert state.manager_node == PRIMARY


async def test_high_availability_reads_groups_on_a_cluster_that_still_has_them() -> None:
    """A cluster part-way through the upgrade still answers the old endpoint,
    and its answer is the one to use."""
    client, _ = client_for(
        responses={"/cluster/ha/groups": [{"group": "prefer-primary", "nodes": PRIMARY}]}
    )

    state = await client.high_availability()

    assert [row["group"] for row in state.groups] == ["prefer-primary"]
