"""The plausible first move, and the reading that shows it would have been wrong.

A skill that lists anti-patterns is a document. This is the enforcement: one
scenario per anti-pattern, each built so that acting on the obvious first move
would have caused the harm the skill warns about, and each asserting both that
the tool's output contradicts the move and that a skill body says so.

Both halves matter. Without the tool assertion the warning is prose nobody can
act on; without the skill assertion the tool's output is a field nobody knows to
read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.proxmox.tools.backup_coverage import proxmox_backup_coverage
from integrations.proxmox.tools.guest_pressure import proxmox_guest_pressure
from integrations.proxmox.tools.guest_start_diagnosis import proxmox_guest_start_diagnosis
from integrations.proxmox.tools.quorum_status import proxmox_quorum_status
from integrations.proxmox.tools.reclaimable_space import proxmox_reclaimable_space
from integrations.proxmox.tools.storage_pressure import proxmox_storage_pressure
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, investigating

pytestmark = pytest.mark.unit

SKILLS = Path(__file__).resolve().parents[3] / "capabilities" / "skills"

#: The six methodology skills these scenarios are about.
METHODOLOGY_SKILLS = (
    "proxmox",
    "proxmox_two_node",
    "proxmox_storage",
    "proxmox_guest",
    "proxmox_backup",
    "proxmox_node_host",
)

#: Every Proxmox methodology skill's body, concatenated once, with whitespace
#: collapsed. The anti-pattern assertions read this rather than one file each,
#: because which skill carries a warning is an editorial decision and whether the
#: warning exists is not — and collapsing whitespace means a warning does not
#: stop being present because a line wrapped in the middle of it.
METHODOLOGY = " ".join(
    " ".join((SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower().split())
    for name in METHODOLOGY_SKILLS
)


async def test_clearing_a_lock_whose_task_is_alive_would_have_corrupted_a_live_backup() -> None:
    """The plausible move: the guest is locked and will not start, so clear the lock."""
    running = {
        "upid": "UPID:pve01:0000C9F0:05130000:68943C00:vzdump:9000:root@pam:",
        "type": "vzdump",
        "status": "running",
        "starttime": 1_754_802_900,
        "node": PRIMARY,
        "user": "root@pam",
    }
    with investigating(responses={f"/nodes/{PRIMARY}/tasks": [running]}):
        result = await proxmox_guest_start_diagnosis(PRIMARY, 9000, kind="qemu")

    lock = result.value["lock"]
    assert lock["held"], "the scenario is only interesting because a lock is held"
    assert not lock["orphaned"], "clearing this lock would have cancelled a running backup"
    assert "corrupt" in lock["verdict"].lower()
    assert "clearing a lock whose task is alive" in METHODOLOGY


async def test_forcing_quorum_would_have_been_proposed_on_a_partition_not_a_dead_node() -> None:
    """The plausible move: the survivor is read-only, so lower the expected votes.

    The reading that stops it is that the cluster reports itself unquorate while
    the other node is still *listed* — unreachable from here is not down, and a
    link failure produces exactly this view from both sides at once.
    """
    with investigating(ClusterState.NO_QUORUM):
        result = await proxmox_quorum_status()

    assert not result.value["quorate"]
    assert result.value["offline_nodes"] == [], (
        "both nodes still report online, so this is a partition rather than a node loss and "
        "forcing quorum here would let both halves write"
    )
    assert "running guests" in " ".join(result.value["consequences"])
    assert "forcing quorum" in METHODOLOGY
    assert "may still be running" in METHODOLOGY


async def test_the_largest_reclaimable_item_is_the_only_recovery_point_and_says_so() -> None:
    """The plausible move: the node is short of space, delete the biggest thing."""
    with investigating():
        result = await proxmox_reclaimable_space(SECONDARY)

    snapshots = [item for item in result.value["items"] if item["kind"] == "snapshot"]
    assert snapshots, "the scenario needs a snapshot to be tempted by"
    assert all("recovery point" in item["protects"] for item in snapshots), (
        "a snapshot offered as reclaimable without saying it is the only way back"
    )
    assert all(item["protects"].strip() for item in result.value["items"])
    assert "only recent recovery point" in METHODOLOGY


async def test_restarting_the_guest_would_have_left_the_host_that_killed_it_untouched() -> None:
    """The plausible move: the guest is stalling, restart it."""
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

    assert result.value["memory"]["attribution"] == "host", (
        "restarting the guest here would return it to the same host and the same outcome"
    )
    assert not result.value["memory"]["guest_under_pressure"]
    assert "restarting a guest whose problem is the host" in METHODOLOGY


async def test_a_guest_named_by_a_disabled_job_would_have_read_as_backed_up() -> None:
    """The plausible move: a job names every guest, so every guest is protected."""
    with investigating():
        result = await proxmox_backup_coverage()

    jobs = {job["id"]: job for job in result.value["jobs"]}
    whole_node = jobs["backup-7d831311"]
    assert whole_node["covers_everything"], "the scenario needs a job that names every guest"
    assert not whole_node["enabled"]

    uncovered = {entry["guest"] for entry in result.value["guests_without_an_enabled_job"]}
    assert 9000 in uncovered and 137 in uncovered, (
        "guests covered only by the disabled job read as protected"
    )
    assert "because a job names it" in METHODOLOGY


async def test_a_datastore_reporting_unknown_would_have_read_as_a_datastore_with_room() -> None:
    """The plausible move: the share reports no usage, so it has plenty of space."""
    with investigating():
        result = await proxmox_storage_pressure(PRIMARY)

    stores = {store["name"]: store for store in result.value["datastores"]}
    failed = stores["externo-nfs-pve01"]
    assert failed["used_ratio"] == 0.0, "which is exactly what makes it look like free space"
    assert failed["name"] in result.value["unreachable_datastores"]
    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert "externo-nfs-pve01" in questions
    assert "as empty rather than as unreachable" in METHODOLOGY


async def test_a_monitoring_stack_inside_the_cluster_would_have_reported_nothing_wrong() -> None:
    """The plausible move: the dashboards are green, so the cluster is fine.

    In the node-down corpus every guest that could answer a dashboard is on the
    node that is still up. The cluster's own reading is the only one that
    contains the failure.
    """
    with investigating(ClusterState.NODE_DOWN):
        result = await proxmox_quorum_status()

    assert result.value["offline_nodes"] == [SECONDARY]
    assert result.value["online_nodes"] == [PRIMARY]
    assert not result.value["quorate"] or result.value["quorum_margin"] < 0
    assert "hosted inside it" in METHODOLOGY


def test_silent_degradation_is_a_named_first_class_hypothesis_rather_than_a_last_resort() -> None:
    """A component that logged a warning and exited zero raises nothing to react to."""
    assert "silent degradation" in METHODOLOGY
    assert "exited zero" in METHODOLOGY
    assert "what last succeeded" in METHODOLOGY


def test_every_methodology_skill_carries_an_anti_pattern_section() -> None:
    for name in METHODOLOGY_SKILLS:
        body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "## Anti-patterns" in body, f"{name}: no anti-pattern section"


def test_every_methodology_skill_routes_to_the_estate_and_to_episodic_memory() -> None:
    """A cause proposed without asking what happened last time is a cause guessed."""
    for name in METHODOLOGY_SKILLS:
        body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "recall_similar_incidents" in body, f"{name}: does not reach episodic memory"
        assert "query_service_topology" in body or "topology" in body, (
            f"{name}: does not reach the estate"
        )
