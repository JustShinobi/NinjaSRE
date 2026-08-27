"""Every hypervisor write, driven against a recorded cluster and no live one.

The corpus is the same two-node cluster the investigation tools are read
against, so what is exercised here is behaviour against responses that were
captured rather than invented. Nothing in this file needs an address, a token, or
a hypervisor that is up.

Three properties carry the file.

**A write is preceded by a read, and a changed target stops it.** The precondition
sweep happens against a reading taken inside the same call, so a test that moves
the guest between the proposal and the execution sees a refusal and an untouched
cluster — asserted as "no write was made", which is the only assertion that
distinguishes a refusal from a rollback.

**The task's outcome is the verdict.** Every write is accepted with a ``200`` in
this corpus. Whether it worked is decided by the task it started, so the same
call succeeds or fails purely on what the task reports — which is the failure
mode a control plane reporting the HTTP status would never see.

**Every action is exercised both ways.** The sweep at the bottom drives all
thirteen against a task that succeeds and against one that fails, so no write
ships having only ever been run down its happy path.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from capabilities.tools.remediation.proxmox import DECLARATIONS
from capabilities.tools.remediation.proxmox.components import (
    RestartedVerifier,
    StartedVerifier,
    components_for,
)
from capabilities.tools.remediation.proxmox.escalation import Escalation, escalation_for
from capabilities.tools.remediation.proxmox.plane import (
    HypervisorTaskFailed,
    ProxmoxControlPlane,
)
from capabilities.tools.remediation.proxmox.preconditions import PreconditionRefused
from capabilities.tools.remediation.proxmox.storage import ReclamationPolicyRefused
from config.constants.hypervisor import (
    GUEST_SHUTDOWN_TIMEOUT_SECONDS,
    HARD_STOP_ESCALATION_SECONDS,
)
from core.capability.metadata import SideEffectLevel
from integrations.proxmox.models import GuestStatus, TaskRecord
from platform.autonomy.risk import RiskClass
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    StateSnapshot,
)
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, write_client_for

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

#: The container the corpus runs on the secondary node, unlocked and running.
PLEX = {"node": SECONDARY, "vmid": 100, "kind": "lxc"}

#: The virtual machine on the primary node, which is stopped and carries a lock.
WINDOWS = {"node": PRIMARY, "vmid": 9000, "kind": "qemu"}

#: The container that can actually move: its disk is on ``local-lvm``, which
#: both nodes declare, so a migration of it is not blocked by storage.
MOVABLE = {"node": PRIMARY, "vmid": 137, "kind": "lxc", "target": SECONDARY}

#: A backup of a guest the cluster no longer has, and the disk it left behind.
STALE_BACKUP = "TeraChad:backup/vzdump-lxc-129-2025_07_02-07_00_02.tar.zst"
ORPHAN = "local-lvm:vm-129-disk-0"

#: What each capability is driven with in the sweep at the bottom, and what the
#: single-behaviour tests above reuse.
ARGUMENTS: Mapping[str, dict[str, Any]] = {
    "proxmox_start_guest": dict(PLEX),
    "proxmox_shutdown_guest": dict(PLEX),
    "proxmox_reboot_guest": dict(PLEX),
    "proxmox_stop_guest": dict(PLEX),
    "proxmox_suspend_guest": dict(PLEX),
    "proxmox_resume_guest": dict(PLEX),
    "proxmox_unlock_guest": dict(PLEX),
    "proxmox_migrate_guest": dict(MOVABLE),
    "proxmox_ha_relocate": {"sid": "ct:115", "target": PRIMARY, "group": "dns"},
    "proxmox_reclaim_storage": {
        "node": SECONDARY,
        "datastore": "TeraChad",
        "items": [STALE_BACKUP],
    },
    "proxmox_remove_orphaned_volume": {
        "node": SECONDARY,
        "datastore": "local-lvm",
        "volume": ORPHAN,
    },
    "proxmox_retry_backup": {**PLEX, "storage": "TeraChad"},
    "proxmox_resync_replication": {"node": SECONDARY, "job_id": "100-0", "rate_limit_mbps": 50},
}

#: Readings the corpus does not carry because the investigation tools never ask
#: for them. A datastore's own status is the one a reclamation reads.
OVERLAY: Mapping[str, Any] = {
    f"/nodes/{SECONDARY}/storage/TeraChad/status": {
        "type": "cifs",
        "total": 8_001_000_000_000,
        "used": 7_654_000_000_000,
        "active": 1,
    },
    f"/nodes/{SECONDARY}/storage/local-lvm/status": {
        "type": "lvmthin",
        "total": 375_700_000_000,
        "used": 317_300_000_000,
        "active": 1,
    },
}


def an_action(capability: str, **overrides: Any) -> RemediationAction:
    """Return the action the plane is driven with for ``capability``."""
    arguments = {**ARGUMENTS[capability], **overrides}
    identifier = str(arguments.get("vmid", arguments.get("sid", arguments.get("datastore", "?"))))
    return RemediationAction(
        action_id=f"action-{capability}",
        capability=capability,
        target=RemediationTarget(identifier=identifier, environment="homelab", kind="guest"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ada",
        arguments=arguments,
    )


def a_plane(
    state: ClusterState = ClusterState.HEALTHY,
    *,
    responses: Mapping[str, Any] | None = None,
    task_exit: str = "OK",
    task_log: tuple[str, ...] = (),
) -> tuple[ProxmoxControlPlane, Any]:
    """Return a control plane over the recorded cluster, and the transport behind it."""
    client, transport = write_client_for(
        state,
        responses={**OVERLAY, **dict(responses or {})},
        task_exit=task_exit,
        task_log=task_log,
    )
    return ProxmoxControlPlane(client=client, declarations=DECLARATIONS), transport


async def read_and_change(
    plane: ProxmoxControlPlane, action: RemediationAction
) -> tuple[StateSnapshot, tuple[Any, ...]]:
    """Read the target the way the executor does, then change it."""
    state = await plane.read(action)
    before = StateSnapshot(
        target=str(action.target),
        observed_at=EPOCH,
        values=dict(state.values) if state is not None else {},
        known=state is not None,
    )
    results = await plane.change(action, desired={}, before=before)
    return before, results


# --- Reading ------------------------------------------------------------------


async def test_a_guest_reading_carries_what_every_guest_write_is_verified_against() -> None:
    """Where it lives, what it is doing, what holds it, and how long it has been up."""
    plane, _ = a_plane()

    state = await plane.read(an_action("proxmox_start_guest"))

    assert state is not None
    assert state.values["node"] == SECONDARY
    assert state.values["status"] == "running"
    assert state.values["lock"] == ""
    assert state.values["uptime"] == 813_244
    assert state.sub_targets == ("lxc/100",)


async def test_a_container_reports_no_agent_rather_than_a_silent_one() -> None:
    """A container shares the host kernel and never declares a guest agent."""
    plane, _ = a_plane()

    state = await plane.read(an_action("proxmox_start_guest"))

    assert state is not None
    assert state.values["agent_responds"] is None


async def test_a_running_virtual_machine_with_an_agent_is_asked_whether_it_answers() -> None:
    """ "It reached running" is Proxmox's opinion from outside; the agent is inside."""
    plane, transport = a_plane(
        responses={
            f"/nodes/{PRIMARY}/qemu/9000/status/current": {
                "status": "running",
                "name": "windows-lab",
                "vmid": 9000,
                "uptime": 60,
                "agent": 1,
                "ha": {"managed": 1},
            }
        }
    )

    state = await plane.read(an_action("proxmox_start_guest", **WINDOWS))

    assert state is not None
    assert state.values["agent_responds"] is True
    assert f"/nodes/{PRIMARY}/qemu/9000/agent/get-fsinfo" in transport.seen


async def test_a_cluster_that_did_not_answer_reads_as_unknown_rather_than_as_empty() -> None:
    """An empty snapshot fingerprints to a real value and would compare equal to another."""
    client, transport = write_client_for()
    transport.unreachable = True
    plane = ProxmoxControlPlane(client=client, declarations=DECLARATIONS)

    assert await plane.read(an_action("proxmox_start_guest")) is None


# --- Preconditions, against a reading taken inside the call -------------------


async def test_a_guest_that_migrated_after_the_proposal_stops_the_write() -> None:
    """And nothing is written, which is what makes it a refusal rather than an undo."""
    plane, transport = a_plane()
    action = an_action("proxmox_start_guest")
    stale = StateSnapshot(
        target=str(action.target),
        observed_at=EPOCH,
        values={"node": PRIMARY, "status": "stopped", "lock": "", "uptime": 0},
    )

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=stale)

    assert "target_unchanged" in refused.value.names
    assert transport.writes == []


async def test_a_cluster_without_quorum_refuses_every_configuration_write() -> None:
    """The configuration filesystem is read-only, so the write could not land anyway."""
    plane, transport = a_plane(ClusterState.NO_QUORUM)
    action = an_action("proxmox_start_guest")
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "cluster_quorate" in refused.value.names
    assert "read-only" in str(refused.value)
    assert transport.writes == []


async def test_a_two_node_cluster_with_a_silent_peer_refuses_a_migration() -> None:
    """The ambiguity is named in the refusal, which is what makes it escalatable."""
    plane, transport = a_plane(ClusterState.NODE_DOWN)
    action = an_action("proxmox_migrate_guest")
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "node_not_ambiguously_dead" in refused.value.names
    assert "dead from one that is merely unreachable" in str(refused.value)
    assert transport.writes == []


async def test_a_migration_into_a_node_that_cannot_see_the_disk_is_refused() -> None:
    """``plex`` lives on ``data-pool``, which the cluster declares for one node only."""
    plane, transport = a_plane()
    action = an_action("proxmox_migrate_guest", **{**PLEX, "target": PRIMARY})
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "target_node_sees_storage" in refused.value.names
    assert "data-pool" in str(refused.value)
    assert transport.writes == []


async def test_a_migration_of_a_stopped_guest_refuses_rather_than_going_offline() -> None:
    """Proxmox would move it offline, which is a different action with a different cost."""
    plane, transport = a_plane(
        responses={
            f"/nodes/{PRIMARY}/lxc/137/status/current": {
                "status": "stopped",
                "vmid": 137,
                "uptime": 0,
                "ha": {"managed": 0},
            }
        }
    )
    action = an_action("proxmox_migrate_guest")
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "online_migration_possible" in refused.value.names
    assert "offline migration" in str(refused.value)
    assert transport.writes == []


async def test_unlocking_a_guest_whose_holder_is_alive_is_refused() -> None:
    """A lock cleared while its holder runs gives one guest two writers."""
    plane, transport = a_plane(
        responses={
            f"/nodes/{PRIMARY}/tasks": [
                {
                    "upid": "UPID:pve01:0000C300:05120000:68943B10:vzdump:9000:root@pam:",
                    "type": "vzdump",
                    "status": "running",
                    "starttime": 1_754_802_900,
                }
            ]
        }
    )
    action = an_action("proxmox_unlock_guest", **WINDOWS)
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "holding_task_dead" in refused.value.names
    assert transport.writes == []


async def test_unlocking_a_guest_whose_holder_is_dead_clears_the_lock() -> None:
    """The primary story, end to end: a backup died and left the guest unmanageable."""
    plane, transport = a_plane(
        responses={
            f"/nodes/{PRIMARY}/tasks": [
                {
                    "upid": "UPID:pve01:0000C300:05120000:68943B10:vzdump:9000:root@pam:",
                    "type": "vzdump",
                    "status": "stopped",
                    "exitstatus": "job errors",
                    "starttime": 1_754_802_900,
                    "endtime": 1_754_802_960,
                }
            ]
        }
    )

    _, results = await read_and_change(plane, an_action("proxmox_unlock_guest", **WINDOWS))

    assert transport.writes == [("PUT", f"/nodes/{PRIMARY}/qemu/9000/config?delete=lock")]
    assert [result.changed for result in results] == [True]


async def test_removing_a_volume_a_live_guest_owns_is_refused_at_execution() -> None:
    """Ownership is read now, because a guest created since the proposal is the risk."""
    plane, transport = a_plane(
        responses={
            f"/nodes/{SECONDARY}/storage/local-lvm/content": [
                {"volid": ORPHAN, "size": 34_359_738_368, "vmid": 100},
            ]
        }
    )
    action = an_action("proxmox_remove_orphaned_volume")
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(PreconditionRefused) as refused:
        await plane.change(action, desired={}, before=before)

    assert "volume_belongs_to_no_guest" in refused.value.names
    assert transport.writes == []


async def test_a_reclamation_cannot_be_given_a_policy_instead_of_a_list() -> None:
    """ "Oldest first" is evaluated against whatever the datastore holds at execution."""
    plane, _ = a_plane()
    action = an_action("proxmox_reclaim_storage", items=["oldest first"])

    with pytest.raises(ReclamationPolicyRefused, match="oldest first"):
        await plane.read(action)


# --- The write, and what its task says ----------------------------------------


@pytest.mark.parametrize(
    ("capability", "arguments", "expected"),
    [
        ("proxmox_start_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/start"),
        ("proxmox_shutdown_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/shutdown"),
        ("proxmox_reboot_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/reboot"),
        ("proxmox_stop_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/stop"),
        ("proxmox_suspend_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/suspend"),
        ("proxmox_resume_guest", PLEX, f"/nodes/{SECONDARY}/lxc/100/status/resume"),
    ],
    ids=["start", "shutdown", "reboot", "stop", "suspend", "resume"],
)
async def test_each_guest_lifecycle_write_reaches_its_own_endpoint(
    capability: str, arguments: dict[str, Any], expected: str
) -> None:
    """Six actions, six endpoints, and none of them reached by any of the others."""
    plane, transport = a_plane()

    await read_and_change(plane, an_action(capability, **arguments))

    ((method, path),) = transport.writes
    assert method == "POST"
    assert path.split("?")[0] == expected


@pytest.mark.parametrize("kind", ["lxc", "qemu"])
async def test_a_lifecycle_write_addresses_both_kinds_of_guest(kind: str) -> None:
    """A container and a virtual machine have different endpoints and one action."""
    guest = PLEX if kind == "lxc" else {**WINDOWS, "vmid": 9000}
    plane, transport = a_plane(
        responses={
            f"/nodes/{PRIMARY}/qemu/9000/status/current": {
                "status": "running",
                "vmid": 9000,
                "uptime": 60,
                "ha": {"managed": 1},
            }
        }
    )

    await read_and_change(plane, an_action("proxmox_stop_guest", **guest))

    assert transport.writes[0][1].split("/")[3] == kind


async def test_a_graceful_shutdown_never_asks_proxmox_to_force_the_stop() -> None:
    """The escalation is a separate action; performing it here would launder one act."""
    plane, transport = a_plane()

    await read_and_change(plane, an_action("proxmox_shutdown_guest"))

    ((_, path),) = transport.writes
    assert "status/shutdown" in path
    assert "forceStop=0" in path
    assert f"timeout={GUEST_SHUTDOWN_TIMEOUT_SECONDS}" in path


async def test_a_migration_is_asked_for_online_and_only_online() -> None:
    """The parameter has one correct value, because the offline case is refused."""
    plane, transport = a_plane()

    await read_and_change(plane, an_action("proxmox_migrate_guest"))

    ((_, path),) = transport.writes
    assert "/migrate" in path
    assert "online=1" in path
    assert f"target={SECONDARY}" in path


async def test_a_replication_resync_is_asked_for_under_a_rate_limit() -> None:
    """Corosync runs over the link a resync saturates, so the limit is a parameter."""
    plane, transport = a_plane()

    await read_and_change(plane, an_action("proxmox_resync_replication"))

    ((_, path),) = transport.writes
    assert "schedule_now" in path
    assert "rate=50" in path


async def test_a_successful_write_carries_its_task_identifier_and_outcome() -> None:
    """The identifier is what an operator searches the cluster's own task list by."""
    plane, _ = a_plane(task_log=("starting container", "task OK"))

    _, results = await read_and_change(plane, an_action("proxmox_start_guest"))

    assert len(results) == 1
    assert results[0].changed
    assert "UPID:" in results[0].detail
    assert "finished OK" in results[0].detail
    assert plane.evidence["lxc/100"].succeeded
    assert plane.evidence["lxc/100"].log[-1] == "task OK"


async def test_a_task_that_fails_is_a_failure_even_though_the_api_call_succeeded() -> None:
    """Every write in this corpus is accepted with a 200. The task decides."""
    plane, transport = a_plane(
        task_exit="storage 'externo-nfs-pve01' is not online",
        task_log=("starting container", "unable to open storage"),
    )
    action = an_action("proxmox_start_guest")
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    with pytest.raises(HypervisorTaskFailed) as failed:
        await plane.change(action, desired={}, before=before)

    assert transport.writes, "the write was made; it is the task that did not succeed"
    assert failed.value.exit_status == "storage 'externo-nfs-pve01' is not online"
    assert failed.value.upid.startswith("UPID:")
    assert "unable to open storage" in str(failed.value)
    assert "returning success is not the action succeeding" in str(failed.value)


async def test_a_reclamation_reports_one_result_per_item_it_was_given() -> None:
    """Partial success is the ordinary outcome of acting on a live system."""
    plane, transport = a_plane()

    _, results = await read_and_change(plane, an_action("proxmox_reclaim_storage"))

    assert [result.identifier for result in results] == [STALE_BACKUP]
    assert [method for method, _ in transport.writes] == ["DELETE"]


# --- Verification -------------------------------------------------------------


def snapshot(**values: Any) -> StateSnapshot:
    """Return a snapshot of ``values`` for a verifier to read."""
    return StateSnapshot(target="lxc/100@homelab", observed_at=EPOCH, values=dict(values))


def test_a_start_that_succeeded_and_immediately_crashed_verifies_as_ineffective() -> None:
    """The API call worked, the task worked, and the guest is not running."""
    action = an_action("proxmox_start_guest")
    before = snapshot(status="stopped", agent_responds=None)
    after = snapshot(status="stopped", agent_responds=None)

    divergences = StartedVerifier().verify(action, before=before, after=after)

    assert divergences
    assert divergences[0].field_name == "status"


def test_a_start_whose_guest_agent_never_answered_verifies_as_ineffective() -> None:
    """It booted and it did not come up, and only the agent tells the two apart."""
    action = an_action("proxmox_start_guest")

    divergences = StartedVerifier().verify(
        action,
        before=snapshot(status="stopped", agent_responds=None),
        after=snapshot(status="running", agent_responds=False),
    )

    assert divergences
    assert divergences[0].field_name == "agent_responds"


def test_a_start_of_a_guest_with_no_agent_is_not_reported_as_broken() -> None:
    """A container declares no agent, and treating that as a failure fails every one."""
    action = an_action("proxmox_start_guest")

    assert (
        StartedVerifier().verify(
            action,
            before=snapshot(status="stopped", agent_responds=None),
            after=snapshot(status="running", agent_responds=None),
        )
        == ()
    )


def test_a_reboot_that_never_happened_verifies_as_ineffective() -> None:
    """A reboot ends where it started, so only uptime distinguishes it from nothing."""
    action = an_action("proxmox_reboot_guest")

    divergences = RestartedVerifier().verify(
        action,
        before=snapshot(status="running", uptime=813_244),
        after=snapshot(status="running", uptime=813_304),
    )

    assert divergences
    assert divergences[0].field_name == "uptime"


def test_a_reboot_that_happened_verifies_as_effective() -> None:
    """The other half, so the verifier cannot pass by refusing everything."""
    action = an_action("proxmox_reboot_guest")

    assert (
        RestartedVerifier().verify(
            action,
            before=snapshot(status="running", uptime=813_244),
            after=snapshot(status="running", uptime=42),
        )
        == ()
    )


def test_a_migration_that_moved_the_guest_and_left_it_stopped_verifies_as_ineffective() -> None:
    """Proxmox accepted it, the guest is on the far node, and it is not running."""
    declaration = DECLARATIONS["proxmox_migrate_guest"]
    components = components_for(declaration)
    action = an_action("proxmox_migrate_guest")

    divergences = components.verifier.verify(
        action,
        before=snapshot(node=PRIMARY, status="running", lock=""),
        after=snapshot(node=SECONDARY, status="stopped", lock=""),
    )

    assert divergences
    assert [found.field_name for found in divergences] == ["status"]


# --- The escalation from graceful to forceful ---------------------------------


def a_guest(status: str) -> GuestStatus:
    """Return the guest an escalation is decided about."""
    return GuestStatus(vmid=100, kind="lxc", node=SECONDARY, status=status, name="plex")


def an_attempt(*, finished: bool) -> TaskRecord:
    """Return the graceful shutdown task, finished or still going."""
    return TaskRecord(
        upid="UPID:pve02:1:1:1:vzshutdown:100:root@pam:",
        task_type="vzshutdown",
        status="stopped" if finished else "running",
        exit_status="OK" if finished else "",
        ended_at=1_754_803_010 if finished else 0,
    )


def test_a_graceful_shutdown_that_worked_escalates_to_nothing() -> None:
    """The escalation exists for the case where the polite request did not work."""
    assert (
        escalation_for(
            a_guest("stopped"),
            attempt=an_attempt(finished=True),
            waited_seconds=HARD_STOP_ESCALATION_SECONDS * 2,
        )
        is None
    )


def test_a_guest_shutting_down_cleanly_and_slowly_is_not_hard_stopped() -> None:
    """Slow is not stuck. A database flushing a large buffer pool is working."""
    assert (
        escalation_for(
            a_guest("running"),
            attempt=an_attempt(finished=False),
            waited_seconds=HARD_STOP_ESCALATION_SECONDS * 4,
        )
        is None
    )


def test_no_escalation_is_due_before_the_declared_timeout() -> None:
    """The timeout is declared so that "we waited long enough" is a fact, not a mood."""
    assert (
        escalation_for(
            a_guest("running"),
            attempt=an_attempt(finished=True),
            waited_seconds=HARD_STOP_ESCALATION_SECONDS - 1,
        )
        is None
    )


def test_a_graceful_shutdown_that_finished_without_stopping_the_guest_escalates() -> None:
    """And the escalation is recorded, with the reason and the attempt it followed."""
    escalation = escalation_for(
        a_guest("running"),
        attempt=an_attempt(finished=True),
        waited_seconds=HARD_STOP_ESCALATION_SECONDS,
    )

    assert isinstance(escalation, Escalation)
    assert escalation.from_capability == "proxmox_shutdown_guest"
    assert escalation.to_capability == "proxmox_stop_guest"
    assert escalation.attempt.startswith("UPID:")
    assert "did not close its own files" in escalation.describe()
    assert escalation.to_record()["risk_class"] == RiskClass.CRITICAL.value


def test_the_hard_stop_is_classified_separately_from_the_shutdown_it_follows() -> None:
    """An escalation that inherited the first class would launder one act into another."""
    escalation = escalation_for(
        a_guest("running"),
        attempt=an_attempt(finished=True),
        waited_seconds=HARD_STOP_ESCALATION_SECONDS,
    )

    assert escalation is not None
    assert escalation.escalates
    assert escalation.risk_class is RiskClass.CRITICAL


# --- Every action, both ways --------------------------------------------------


@pytest.mark.parametrize("capability", sorted(ARGUMENTS), ids=sorted(ARGUMENTS))
async def test_every_write_runs_against_a_recorded_task_that_succeeds(capability: str) -> None:
    """No live cluster, and no action shipping having only ever been imagined."""
    plane, transport = a_plane(task_log=("started", "task OK"))

    _, results = await read_and_change(plane, an_action(capability))

    assert transport.writes, f"{capability} reached no endpoint"
    assert results, f"{capability} reported nothing about what it did"
    assert all(result.changed for result in results), capability


@pytest.mark.parametrize("capability", sorted(ARGUMENTS), ids=sorted(ARGUMENTS))
async def test_every_write_runs_against_a_recorded_task_that_fails(capability: str) -> None:
    """The failing half, which is the half a happy-path corpus never exercises.

    A configuration edit has no task to fail — Proxmox applies it synchronously —
    so those report success here, and that is the honest outcome rather than an
    exemption: there is no task outcome to disagree with.
    """
    plane, _ = a_plane(task_exit="job errors", task_log=("started", "job errors"))
    declaration = DECLARATIONS[capability]
    action = an_action(capability)
    state = await plane.read(action)
    assert state is not None
    before = StateSnapshot(target=str(action.target), observed_at=EPOCH, values=dict(state.values))

    if declaration.method == "PUT":
        results = await plane.change(action, desired={}, before=before)
        assert all(result.changed for result in results), capability
        return

    with pytest.raises(HypervisorTaskFailed) as failed:
        await plane.change(action, desired={}, before=before)

    assert failed.value.exit_status == "job errors"
    assert "job errors" in str(failed.value)
