"""Phase 2: storage, at the four levels that fail independently of one another.

The datastore percentage is the number everybody watches and the least useful of
the four. Underneath it sits a thin pool with two percentages that fail
differently, and underneath that each guest's own volume; beside all three sit
the physical drives, whose firmware says ``PASSED`` right up until it does not.

The readings here exist because of specific wrong answers:

- **A pool that is healthy and full.** ZFS reports ``ONLINE`` at 96% capacity and
  writes have already slowed by an order of magnitude. Health is not capacity.
- **A verdict that is not the attributes.** SMART says ``PASSED`` while pending
  sectors climb. The verdict changes last.
- **A list of deletable things with no idea what they protect.** The largest
  reclaimable item is very often the only recent recovery point, and a report
  that ranks by size and stops there is a report that recommends deleting it.
- **A datastore reporting ``unknown``.** That is Proxmox saying it cannot reach
  the share at all. It is not a fill level and it is not an empty datastore.
"""

from __future__ import annotations

import pytest

from integrations.proxmox.investigation import ZFS_CAPACITY_DEGRADED_PERCENT
from integrations.proxmox.tools.datastore_availability import proxmox_datastore_availability
from integrations.proxmox.tools.disk_health import proxmox_disk_health
from integrations.proxmox.tools.orphaned_volumes import proxmox_orphaned_volumes
from integrations.proxmox.tools.reclaimable_space import proxmox_reclaimable_space
from integrations.proxmox.tools.storage_pressure import proxmox_storage_pressure
from integrations.proxmox.tools.zfs_health import proxmox_zfs_health
from tests.support.proxmox import (
    PRIMARY,
    SECONDARY,
    ZFS_POOL_DETAIL,
    ZFS_POOLS,
    ClusterState,
    investigating,
)

pytestmark = pytest.mark.unit

#: A pool that is entirely healthy and dangerously full. The state ZFS reports is
#: ``ONLINE`` and every device is fine; the only thing wrong is the number nobody
#: watches, which is why this fixture exists separately from a degraded one.
_FULL_POOL = {
    **ZFS_POOLS[0],
    "size": 4_000_000_000_000,
    "alloc": 3_840_000_000_000,
    "free": 160_000_000_000,
}


def _with_zfs(node: str = SECONDARY, **overrides: object) -> dict[str, object]:
    """Return the recorded responses a node with one ZFS pool would give."""
    pool = {**_FULL_POOL, **overrides}
    return {
        f"/nodes/{node}/disks/zfs": [pool],
        f"/nodes/{node}/disks/zfs/tank": ZFS_POOL_DETAIL,
    }


# --- Datastore, pool and volume pressure --------------------------------------


async def test_storage_pressure_names_the_largest_consumers_of_each_datastore() -> None:
    """A datastore at 84% with no idea what is in it is a number, not a finding."""
    with investigating():
        result = await proxmox_storage_pressure(SECONDARY)

    consumers = {
        entry["datastore"]: entry["largest_consumers"] for entry in result.value["consumers"]
    }
    assert consumers["local-lvm"], "no consumer was reported for a datastore that has contents"
    largest = consumers["local-lvm"][0]
    assert largest["volid"] == "local-lvm:vm-100-disk-0"
    assert largest["size_bytes"] == 107_374_182_400


async def test_thin_pool_metadata_exhaustion_is_reported_apart_from_data_exhaustion() -> None:
    """The degraded pool has ample data space and no metadata space."""
    with investigating(ClusterState.DEGRADED):
        result = await proxmox_storage_pressure(SECONDARY)

    pools = {pool["name"]: pool for pool in result.value["thin_pools"]}
    assert pools["data"]["metadata_critical"]
    assert pools["data"]["data_percent"] < 90
    assert "metadata" in result.evidence[0].summary


async def test_a_datastore_reporting_unknown_is_not_reported_as_a_fill_level() -> None:
    with investigating():
        result = await proxmox_storage_pressure(PRIMARY)

    assert result.value["unreachable_datastores"] == ["externo-nfs-pve01"]


# --- ZFS ----------------------------------------------------------------------


async def test_a_healthy_zfs_pool_above_the_capacity_threshold_is_flagged() -> None:
    """Every device online, no errors, and the write path already degraded."""
    with investigating(responses=_with_zfs()):
        result = await proxmox_zfs_health(SECONDARY)

    pool = result.value["pools"][0]
    assert pool["state"] == "ONLINE"
    assert pool["capacity_percent"] > ZFS_CAPACITY_DEGRADED_PERCENT
    assert pool["capacity_degrades_performance"]
    assert "capacity" in result.evidence[0].summary.lower()


async def test_per_device_state_and_error_counts_are_reported_not_only_the_pool_word() -> None:
    with investigating(responses=_with_zfs()):
        result = await proxmox_zfs_health(SECONDARY)

    devices = {device["name"]: device for device in result.value["pools"][0]["devices"]}
    assert devices["sdd"]["checksum_errors"] == 2
    assert devices["sda"]["checksum_errors"] == 0


async def test_the_scrub_line_is_parsed_into_an_age_rather_than_repeated_as_prose() -> None:
    with investigating(responses=_with_zfs()):
        result = await proxmox_zfs_health(SECONDARY)

    scrub = result.value["pools"][0]["scrub"]
    assert scrub["finished_at"].startswith("2025-06-08")
    assert scrub["age_days"] > 0


async def test_fragmentation_is_carried_because_nothing_else_reports_it() -> None:
    with investigating(responses=_with_zfs()):
        result = await proxmox_zfs_health(SECONDARY)

    assert result.value["pools"][0]["fragmentation_percent"] == 47


async def test_a_node_with_no_zfs_reports_the_question_as_inapplicable() -> None:
    """Neither reference node has a pool, and that is not a failure or an empty result."""
    with investigating():
        result = await proxmox_zfs_health(SECONDARY)

    assert result.value["applicable"] is False
    assert result.value["pools"] == []
    assert "no zfs" in result.evidence[0].summary.lower()


# --- Physical disks -----------------------------------------------------------


async def test_smart_attributes_that_predict_failure_are_reported_apart_from_the_verdict() -> None:
    with investigating():
        result = await proxmox_disk_health(SECONDARY)

    disks = {disk["device"]: disk for disk in result.value["disks"]}
    spinning = disks["/dev/sda"]
    assert spinning["smart_health"] == "PASSED"
    predictive = {entry["name"]: entry for entry in spinning["predictive_attributes"]}
    assert predictive["Current_Pending_Sector"]["raw"] == "24"
    assert predictive["Reallocated_Sector_Ct"]["raw"] == "184"


async def test_a_disk_whose_verdict_still_passes_while_its_attributes_climb_is_called_out() -> None:
    with investigating():
        result = await proxmox_disk_health(SECONDARY)

    disks = {disk["device"]: disk for disk in result.value["disks"]}
    assert disks["/dev/sda"]["predicts_failure"]
    assert not disks["/dev/nvme0n1"]["predicts_failure"]


async def test_each_disk_says_what_it_backs_and_names_what_it_could_not_establish() -> None:
    with investigating(responses=_with_zfs()):
        result = await proxmox_disk_health(SECONDARY)

    disks = {disk["device"]: disk for disk in result.value["disks"]}
    assert disks["/dev/sda"]["backs"] == ["tank"]
    assert disks["/dev/nvme0n1"]["backs"] == []
    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert "/dev/nvme0n1" in questions


# --- Reclaimable space --------------------------------------------------------


async def test_no_reclaimable_item_is_returned_without_saying_what_it_protects() -> None:
    """Asserted structurally over every entry, not by reading the report."""
    with investigating():
        result = await proxmox_reclaimable_space(SECONDARY)

    assert result.value["items"], "a cluster with snapshots and backups reclaimed nothing"
    for item in result.value["items"]:
        assert item["protects"].strip(), f"{item['reference']} was listed with nothing it protects"
        # A snapshot's size is not published by Proxmox at all. Saying so is the
        # honest answer; reporting zero as though it were measured is not.
        assert item["reclaims_bytes"] > 0 or not item["reclaims_bytes_known"]


async def test_a_snapshot_is_reported_with_its_guest_and_its_age() -> None:
    with investigating():
        result = await proxmox_reclaimable_space(SECONDARY)

    snapshots = [item for item in result.value["items"] if item["kind"] == "snapshot"]
    assert snapshots
    assert any("100" in item["protects"] for item in snapshots)


async def test_a_backup_is_reported_with_the_retention_rule_that_keeps_it() -> None:
    with investigating():
        result = await proxmox_reclaimable_space(SECONDARY)

    backups = [item for item in result.value["items"] if item["kind"] == "backup"]
    assert backups
    assert any("retention" in item["protects"].lower() for item in backups)


async def test_a_thousand_snapshots_produce_a_bounded_ranked_result_that_says_so() -> None:
    """Bounded by ranking rather than by truncation, and it states what it ranked by."""
    with investigating(
        responses={
            f"/nodes/{SECONDARY}/lxc/100/snapshot": [
                {"name": f"auto-{index:04d}", "snaptime": 1_700_000_000 + index}
                for index in range(1_000)
            ]
        }
    ):
        result = await proxmox_reclaimable_space(SECONDARY)

    bound = result.value["bounds"]["items"]
    assert bound["bounded"]
    assert bound["total"] > bound["shown"]
    assert bound["ranked_by"]
    assert len(result.value["items"]) == bound["limit"]


# --- Orphans and reachability -------------------------------------------------


async def test_a_volume_belonging_to_no_guest_is_reported_with_its_former_owner() -> None:
    with investigating():
        result = await proxmox_orphaned_volumes()

    orphans = {entry["volid"]: entry for entry in result.value["orphans"]}
    assert "local-lvm:vm-129-disk-0" in orphans
    assert orphans["local-lvm:vm-129-disk-0"]["former_guest"] == 129


async def test_a_volume_whose_guest_still_exists_is_not_called_an_orphan() -> None:
    with investigating():
        result = await proxmox_orphaned_volumes()

    assert "local-lvm:vm-100-disk-0" not in {entry["volid"] for entry in result.value["orphans"]}


async def test_which_datastores_each_node_can_see_is_reported_from_the_cluster_definition() -> None:
    with investigating():
        result = await proxmox_datastore_availability()

    nodes = {entry["node"]: entry for entry in result.value["nodes"]}
    assert "TeraChad" in nodes[SECONDARY]["declared"]
    assert "TeraChad" not in nodes[PRIMARY]["declared"]
    assert "local-lvm" in nodes[PRIMARY]["declared"]


async def test_a_datastore_declared_on_a_node_but_not_reachable_from_it_is_separated() -> None:
    """Declared and unreachable is a different fact from not declared at all."""
    with investigating():
        result = await proxmox_datastore_availability()

    nodes = {entry["node"]: entry for entry in result.value["nodes"]}
    assert "externo-nfs-pve01" in nodes[PRIMARY]["declared"]
    assert "externo-nfs-pve01" in nodes[PRIMARY]["unreachable"]
    assert "externo-nfs-pve01" not in nodes[PRIMARY]["available"]
