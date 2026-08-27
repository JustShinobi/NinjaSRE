"""Reaching a Proxmox cluster as a control plane, with the checks in the middle.

This is the one place a hypervisor write actually happens, and the order it
happens in is the specification:

1. read the target, now, through the same client the write will use;
2. gather only the facts the capability's declared preconditions ask about;
3. evaluate them, and refuse — before anything is written — if any fails;
4. perform the write, which returns a task identifier rather than a result;
5. poll the task, and report *its* outcome, never the HTTP status.

Step five is the one worth reading twice. Proxmox answers ``200`` to a request it
merely accepted. The task it started may fail thirty seconds later for a reason
the API call had no way to know, and a control plane that reported the acceptance
would report every such failure as a success. So the task's own exit status is
the verdict, its identifier and its log travel with the result, and a task that
failed raises carrying the provider's own words.

**A write is never retried and never fails over.** A read may be tried against the
next node in the ring because reading twice is free. A write may not: the first
attempt may have landed, and the second would be a change nobody approved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from capabilities.tools.remediation.control_plane import ControlPlaneState
from capabilities.tools.remediation.proxmox.declaration import (
    ProxmoxRemediation,
    WriteCategory,
)
from capabilities.tools.remediation.proxmox.preconditions import (
    Facts,
    Precondition,
    PreconditionRefused,
    evaluate,
)
from capabilities.tools.remediation.proxmox.risk import ReclaimableItem
from capabilities.tools.remediation.proxmox.storage import items_of
from config.constants.hypervisor import (
    DEFAULT_REPLICATION_RATE_LIMIT_MBPS,
    GUEST_SHUTDOWN_TIMEOUT_SECONDS,
)
from integrations._base.errors import IntegrationError
from integrations.proxmox.models import GuestStatus, TaskRecord
from integrations.proxmox.writes import ProxmoxWriteClient
from platform.remediation.errors import RemediationError
from platform.remediation.models import RemediationAction, StateSnapshot, SubTargetResult

#: How many lines of a task's log travel with the result. The whole log is
#: bounded at five hundred lines by the client; a hundred of those in an
#: execution record is a record nobody opens, and the last twenty are the ones
#: that say what went wrong.
EVIDENCE_LOG_LINES: Final = 20

#: The task type Proxmox gives a backup run. Recognised rather than matched
#: loosely, because "is a backup running against this datastore" is what decides
#: whether a reclamation is about to break one.
BACKUP_TASK_TYPE: Final = "vzdump"

#: What the word in a guest's lock is called in its task history. Proxmox names
#: the lock after the *operation* and the task after the *tool* — a backup's
#: lock says ``backup`` and its task says ``vzdump`` — so finding the holder
#: needs the translation. Declared rather than guessed by substring, because
#: this is what decides whether a lock is orphaned or held by live work.
LOCK_TASK_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "backup": ("vzdump",),
    "migrate": ("qmigrate", "vzmigrate"),
    "snapshot": ("qmsnapshot", "vzsnapshot"),
    "snapshot-delete": ("qmdelsnapshot", "vzdelsnapshot"),
    "rollback": ("qmrollback", "vzrollback"),
    "clone": ("qmclone", "vzclone"),
    "create": ("qmcreate", "vzcreate"),
    "disk": ("resize", "move"),
    "suspending": ("qmsuspend",),
    "suspended": ("qmsuspend",),
}


class HypervisorTaskFailed(RemediationError):
    """A write was accepted and the task it started did not succeed.

    Its own type, and it carries the identifier, the exit status and the tail of
    the log — because the question an operator has next is "what did Proxmox
    say", and the answer is not "the API returned 200".
    """

    def __init__(self, capability: str, target: str, task: TaskRecord, log: Sequence[str]) -> None:
        tail = "\n  ".join(log) or "the task left no log"
        super().__init__(
            f"{capability!r} against {target!r} was accepted by Proxmox and its task did not "
            f"succeed. Task {task.upid} finished with {task.exit_status or task.status!r}. "
            f"The API call returning success is not the action succeeding.\n  {tail}"
        )
        self.capability = capability
        self.target = target
        self.upid = task.upid
        self.exit_status = task.exit_status or task.status
        self.log = tuple(log)


@dataclass(frozen=True, slots=True)
class TaskEvidence:
    """What one write left behind, in the form an incident carries."""

    upid: str
    exit_status: str
    succeeded: bool
    log: tuple[str, ...] = ()

    def describe(self) -> str:
        """Return the one line a sub-target result carries into the execution record."""
        if not self.upid:
            return "applied synchronously; Proxmox started no task for it"
        verdict = "OK" if self.succeeded else self.exit_status or "no exit status"
        tail = " | ".join(self.log[-3:])
        return f"task {self.upid} finished {verdict}" + (f"; log: {tail}" if tail else "")


@dataclass(slots=True)
class ProxmoxControlPlane:
    """A Proxmox cluster, seen as the control plane a remediation changes.

    Holds no credential and cannot: the client it carries reaches the cluster
    through the proxy, which injects the secret at the network edge.
    """

    client: ProxmoxWriteClient
    declarations: Mapping[str, ProxmoxRemediation]
    #: The rate a replication resync is limited to when the action names none.
    rate_limit_mbps: int = DEFAULT_REPLICATION_RATE_LIMIT_MBPS
    #: What the last write left behind, per sub-target. Read by a caller that
    #: wants the evidence structured rather than as the sentence in the record.
    evidence: dict[str, TaskEvidence] = field(default_factory=dict)

    def _client_for(self, action: RemediationAction | None = None) -> ProxmoxWriteClient:
        """Return the write client scoped to ``action``'s team, or the shared client."""
        if action is None or not action.team_node_id:
            return self.client
        return self.client.for_team(action.team_node_id)

    # -- reading --------------------------------------------------------------

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        """Return what the target holds, or ``None`` when it could not be read."""
        declaration = self.declarations.get(action.capability)
        if declaration is None:
            return None
        try:
            return await self._read_for(declaration, action)
        except IntegrationError:
            # A cluster that did not answer is "we could not tell", which blocks
            # the action. Raising here would make an unreachable node an error
            # about the request rather than a fact about the estate.
            return None

    async def _read_for(
        self, declaration: ProxmoxRemediation, action: RemediationAction
    ) -> ControlPlaneState | None:
        """Return the reading one category of write is verified against."""
        if declaration.category in {WriteCategory.GUEST_LIFECYCLE, WriteCategory.MOVEMENT}:
            return await self._read_guest(action)
        if declaration.category is WriteCategory.HIGH_AVAILABILITY:
            return await self._read_ha(action)
        if declaration.category is WriteCategory.STORAGE:
            return await self._read_storage(declaration, action)
        if declaration.category is WriteCategory.BACKUP:
            return await self._read_backup(action)
        return await self._read_replication(action)

    async def _read_guest(self, action: RemediationAction) -> ControlPlaneState:
        """Return one guest's node, state, lock, uptime and whether its agent answers."""
        node, vmid, kind = _guest_of(action)
        client = self._client_for(action)
        guest = await client.guest_status(node, vmid, kind=kind)
        return ControlPlaneState(
            values={
                "node": guest.node,
                "status": guest.status,
                "lock": guest.lock,
                "uptime": guest.uptime_seconds,
                "agent_responds": await self._agent_answers(guest, action=action),
            },
            sub_targets=(f"{kind}/{vmid}",),
        )

    async def _agent_answers(
        self, guest: GuestStatus, *, action: RemediationAction | None = None
    ) -> bool | None:
        """Return whether the guest's own agent replied, or ``None`` when it has none.

        ``None`` rather than ``False`` for a guest that declares no agent, and a
        container never declares one. "Nothing inside is reachable to ask" and
        "we asked and got nothing" are different sentences, and only the second
        says anything about the guest.
        """
        if guest.is_container or not guest.agent_declared or guest.status != "running":
            return None
        reading = await self._client_for(action).guest_agent_filesystems(guest.node, guest.vmid)
        return reading.available

    async def _read_ha(self, action: RemediationAction) -> ControlPlaneState:
        """Return what the high-availability manager holds about one resource."""
        sid = str(action.arguments.get("sid", ""))
        state = await self._client_for(action).high_availability()
        service = next((row for row in state.services if str(row.get("sid", "")) == sid), {})
        definition = next((row for row in state.resources if str(row.get("sid", "")) == sid), {})
        return ControlPlaneState(
            values={
                "ha_node": str(service.get("node", "")),
                "ha_state": str(service.get("state", definition.get("state", ""))),
                "ha_group": str(definition.get("group", "")),
            },
            sub_targets=(sid,) if sid else (),
        )

    async def _read_storage(
        self, declaration: ProxmoxRemediation, action: RemediationAction
    ) -> ControlPlaneState:
        """Return which of the named volumes are still there, and who owns them."""
        node = str(action.arguments.get("node", ""))
        datastore = str(action.arguments.get("datastore", ""))
        named = _named_volumes(action)
        present = await self._present(node, datastore, named, action=action)
        owners = await self._owners(node, datastore, tuple(present), action=action)

        if declaration.capability == "proxmox_reclaim_storage":
            reading = await self._client_for(action).datastore_status(node, datastore)
            store = reading.value
            return ControlPlaneState(
                values={
                    "items": list(present),
                    "used_bytes": store.used_bytes if store is not None else 0,
                },
                sub_targets=tuple(present),
            )
        return ControlPlaneState(
            values={"volumes": list(present), "owners": dict(owners)},
            sub_targets=tuple(present),
        )

    async def _read_backup(self, action: RemediationAction) -> ControlPlaneState:
        """Return whether the guest's most recent backup worked, and when it ran."""
        node, vmid, _ = _guest_of(action)
        latest = await self._client_for(action).last_successful_backup(node)
        found = latest.get(vmid)
        return ControlPlaneState(
            values={
                "last_backup_succeeded": found is not None,
                "last_backup_at": found.started_at if found is not None else 0,
            },
            sub_targets=(f"backup/{vmid}",),
        )

    async def _read_replication(self, action: RemediationAction) -> ControlPlaneState:
        """Return one replication job's health, its last sync and where it goes."""
        node = str(action.arguments.get("node", ""))
        job_id = str(action.arguments.get("job_id", ""))
        jobs = await self._client_for(action).replication_jobs(node)
        job = next((row for row in jobs if row.job_id == job_id), None)
        return ControlPlaneState(
            values={
                "failing": job.failing if job is not None else True,
                "last_sync": job.last_sync if job is not None else 0,
                "target": job.target if job is not None else "",
            },
            sub_targets=(job_id,) if job_id else (),
        )

    async def _present(
        self,
        node: str,
        datastore: str,
        named: tuple[str, ...],
        *,
        action: RemediationAction | None = None,
    ) -> tuple[str, ...]:
        """Return which of ``named`` the datastore still holds."""
        contents = await self._client_for(action).datastore_contents(node, datastore)
        held = {str(row.get("volid", "")) for row in contents}
        return tuple(volume for volume in named if volume in held)

    async def _owners(
        self,
        node: str,
        datastore: str,
        volumes: tuple[str, ...],
        *,
        action: RemediationAction | None = None,
    ) -> dict[str, int]:
        """Return which of ``volumes`` a guest that still exists references.

        Read at execution rather than at proposal. A guest created between the
        two is exactly the volume nobody would think to re-check, and the whole
        point of the orphan check is that it holds at the moment of deletion.
        """
        if not volumes:
            return {}
        client = self._client_for(action)
        contents = await client.datastore_contents(node, datastore)
        resources = await client.cluster_resources()
        alive = {
            int(row.get("vmid", 0) or 0)
            for row in resources
            if row.get("type") in {"lxc", "qemu"} and row.get("vmid")
        }
        owners: dict[str, int] = {}
        for row in contents:
            volume = str(row.get("volid", ""))
            owner = int(row.get("vmid", 0) or 0)
            if volume in volumes and owner in alive:
                owners[volume] = owner
        return owners

    # -- changing -------------------------------------------------------------

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        """Perform ``action``, having re-checked that it is still the right thing to do.

        ``desired`` is what the capability declared it intends, and it is not read
        here: which endpoint to reach follows from the capability, and taking it
        from a mapping instead would be a place a generated value reached a
        production API.
        """
        del desired
        declaration = self.declarations[action.capability]
        facts = await self.gather(declaration, action)
        refusals = evaluate(declaration.preconditions, facts=facts, before=before)
        if refusals:
            raise PreconditionRefused(action.capability, str(action.target), refusals)
        return await self._perform(declaration, action)

    async def gather(self, declaration: ProxmoxRemediation, action: RemediationAction) -> Facts:
        """Return a fresh reading of everything ``declaration``'s preconditions ask about.

        Only what is asked about. A guest start pays for the guest and the
        cluster; it does not pay for a datastore listing it will never consult.
        """
        wanted = set(declaration.preconditions)
        facts: dict[str, Any] = {}

        if Precondition.TARGET_UNCHANGED in wanted:
            state = await self.read(action)
            facts["identity"] = (
                None
                if state is None
                else {name: state.values.get(name) for name in declaration.identity_fields}
            )

        if wanted & {Precondition.CLUSTER_QUORATE, Precondition.NODE_NOT_AMBIGUOUSLY_DEAD}:
            facts.update(await self._cluster_facts(action))

        if wanted & {Precondition.GUEST_UNLOCKED, Precondition.HOLDING_TASK_DEAD}:
            facts.update(await self._guest_facts(action))

        if Precondition.TARGET_NODE_SEES_STORAGE in wanted:
            facts.update(await self._storage_visibility(action))

        if Precondition.ONLINE_MIGRATION_POSSIBLE in wanted:
            facts["online_migration_blocker"] = await self._online_blocker(action)

        if Precondition.NO_SCHEDULED_BACKUP_COLLISION in wanted:
            facts["seconds_until_scheduled_backup"] = await self._until_scheduled_backup(action)

        if wanted & {
            Precondition.VOLUME_BELONGS_TO_NO_GUEST,
            Precondition.NO_RUNNING_BACKUP_NEEDS_THE_SPACE,
            Precondition.NOT_DELETING_A_BACKUP_TO_MAKE_ROOM,
        }:
            facts.update(await self._reclamation_facts(action))

        return Facts(**facts)

    async def _cluster_facts(self, action: RemediationAction | None = None) -> dict[str, Any]:
        """Return membership and quorum as they stand right now."""
        status = await self._client_for(action).cluster_status()
        return {
            "quorate": status.quorate,
            "is_clustered": status.is_clustered,
            "members": tuple(member.name for member in status.members),
            "online_nodes": status.online_nodes,
            "contributing_quorum_device": bool(status.quorum_device)
            and not status.has_non_contributing_quorum_device,
        }

    async def _guest_facts(self, action: RemediationAction) -> dict[str, Any]:
        """Return the guest's own state and, when it is locked, what holds the lock."""
        node, vmid, kind = _guest_of(action)
        client = self._client_for(action)
        guest = await client.guest_status(node, vmid, kind=kind)
        holder = await self._lock_holder(guest, action=action) if guest.lock else None
        return {
            "guest_node": guest.node,
            "guest_status": guest.status,
            "guest_lock": guest.lock,
            "holding_task": holder,
        }

    async def _lock_holder(
        self, guest: GuestStatus, *, action: RemediationAction | None = None
    ) -> TaskRecord | None:
        """Return the most recent task of the kind the lock names, or ``None``.

        Proxmox writes the *operation* into the lock — ``backup``, ``migrate``,
        ``snapshot`` — and names the task after the tool that performs it, which
        is a different word: a backup's lock says ``backup`` and its task says
        ``vzdump``. ``LOCK_TASK_TYPES`` is that translation, and it is a
        declaration rather than a substring guess because guessing here decides
        whether a lock is orphaned or held by live work.

        A lock whose word matches nothing recent is a lock with no identifiable
        holder, and that is reported as unknown rather than assumed dead.
        """
        history = await self._client_for(action).guest_tasks(
            guest.node, guest.vmid, kind=guest.kind
        )
        word = guest.lock.strip().lower()
        if not word:
            return None
        wanted = (word, *LOCK_TASK_TYPES.get(word, ()))
        for task in history:
            performed = task.task_type.lower()
            if any(fragment in performed for fragment in wanted):
                return task
        return None

    async def _storage_visibility(self, action: RemediationAction) -> dict[str, Any]:
        """Return which datastores the guest is on and which the target node can see."""
        node, vmid, kind = _guest_of(action)
        target = str(action.arguments.get("target", ""))
        client = self._client_for(action)
        configuration = await client.guest_configuration(node, vmid, kind=kind)
        stores = await client.node_storage(target) if target else ()
        return {
            "target_node": target,
            "guest_datastores": _datastores_of(configuration),
            "target_node_datastores": tuple(store.name for store in stores if store.is_available),
        }

    async def _online_blocker(self, action: RemediationAction) -> str:
        """Return what stops this guest moving without being stopped, or the empty string.

        A stopped guest counts as a blocker rather than as a trivially easy move.
        Proxmox would perform the move offline, which is a different action with
        a different cost, and performing it under the name of the one that was
        approved is exactly the substitution this refuses.
        """
        node, vmid, kind = _guest_of(action)
        client = self._client_for(action)
        guest = await client.guest_status(node, vmid, kind=kind)
        if guest.status != "running":
            return (
                f"the guest is {guest.status or 'not running'}, so the move Proxmox would "
                f"perform is an offline one"
            )
        configuration = await client.guest_configuration(node, vmid, kind=kind)
        passthrough = sorted(
            str(key) for key in configuration if str(key).startswith(("hostpci", "usb"))
        )
        if passthrough:
            return (
                f"it declares {', '.join(passthrough)}, which is hardware in one machine; "
                f"the migration would be accepted and would fail at the far end"
            )
        return ""

    async def _until_scheduled_backup(self, action: RemediationAction) -> int | None:
        """Return how soon a scheduled backup covering this guest starts, in seconds.

        ``None`` when nothing scheduled covers it. A job that exists and is
        switched off covers nothing, which is the most dangerous shape a backup
        job has and the reason ``enabled`` is read rather than assumed.
        """
        node, vmid, _ = _guest_of(action)
        client = self._client_for(action)
        jobs = await client.backup_jobs()
        covering = [
            job
            for job in jobs
            if job.enabled and (job.covers_everything or vmid in job.vmids) and job.schedule
        ]
        if not covering:
            return None
        clock = await client.node_time(node)
        now = int(clock.get("time", 0) or 0)
        due = [_seconds_until(job.schedule, now) for job in covering]
        soonest = [value for value in due if value is not None]
        return min(soonest) if soonest else None

    async def _reclamation_facts(self, action: RemediationAction) -> dict[str, Any]:
        """Return what the datastore holds, who owns it, and what is writing to it."""
        node = str(action.arguments.get("node", ""))
        datastore = str(action.arguments.get("datastore", ""))
        named = _named_volumes(action)
        client = self._client_for(action)
        contents = await client.datastore_contents(node, datastore)
        rows = {str(row.get("volid", "")): row for row in contents}
        items = tuple(
            ReclaimableItem(
                volume_id=volume,
                content=str(rows[volume].get("content", "")),
                size_bytes=int(rows[volume].get("size", 0) or 0),
            )
            for volume in named
            if volume in rows
        )
        owners = await self._owners(node, datastore, named, action=action)
        running = await self._running_backup(node, datastore, action=action)
        reading = await client.datastore_status(node, datastore)
        store = reading.value
        free = (store.total_bytes - store.used_bytes) if store is not None else 0
        return {
            "items": items,
            "volume_owners": owners,
            "running_backup_bytes_needed": running,
            "free_bytes": max(free, 0),
            "making_room_for_a_backup": running > 0,
        }

    async def _running_backup(
        self, node: str, datastore: str, *, action: RemediationAction | None = None
    ) -> int:
        """Return how much a backup running against ``datastore`` may still need.

        Estimated from the guest's own configured disk, which is the largest a
        full backup of it could be. An estimate rather than a measurement,
        because Proxmox does not publish a running task's remaining bytes — and
        an over-estimate refuses a reclamation that would have been fine, which
        is the failure direction to be on.
        """
        del datastore
        client = self._client_for(action)
        tasks = await client.node_tasks(node)
        running = [
            task for task in tasks if task.task_type == BACKUP_TASK_TYPE and not task.finished
        ]
        if not running:
            return 0
        resources = await client.cluster_resources()
        sizes = {
            int(row.get("vmid", 0) or 0): int(row.get("maxdisk", 0) or 0)
            for row in resources
            if row.get("vmid")
        }
        return sum(sizes.get(task.vmid, 0) for task in running)

    # -- performing -----------------------------------------------------------

    async def _perform(
        self, declaration: ProxmoxRemediation, action: RemediationAction
    ) -> tuple[SubTargetResult, ...]:
        """Reach the endpoint this capability declared, and report what its task did."""
        if declaration.category is WriteCategory.STORAGE:
            return await self._delete_volumes(declaration, action)

        writer = _WRITERS[declaration.capability]
        node = str(action.arguments.get("node", ""))
        upid = await writer(self, action)
        return (
            await self._settled(declaration, action, node=node, upid=upid, piece=_piece(action)),
        )

    async def _delete_volumes(
        self, declaration: ProxmoxRemediation, action: RemediationAction
    ) -> tuple[SubTargetResult, ...]:
        """Delete each named volume, one result per volume, so partial success is sayable."""
        node = str(action.arguments.get("node", ""))
        datastore = str(action.arguments.get("datastore", ""))
        results: list[SubTargetResult] = []
        client = self._client_for(action)
        for volume in _named_volumes(action):
            upid = await client.delete_volume(node, datastore=datastore, volume=volume)
            results.append(
                await self._settled(declaration, action, node=node, upid=upid, piece=volume)
            )
        return tuple(results)

    async def _settled(
        self,
        declaration: ProxmoxRemediation,
        action: RemediationAction,
        *,
        node: str,
        upid: str,
        piece: str,
    ) -> SubTargetResult:
        """Poll the task this write started and return what it actually did.

        A task that failed raises rather than returning ``changed=False``: the
        deployment asked for a change, Proxmox tried and did not make it, and
        that is a failed execution rather than a successful one that happened to
        move nothing.
        """
        del declaration
        if not upid:
            evidence = TaskEvidence(upid="", exit_status="", succeeded=True)
            self.evidence[piece] = evidence
            return SubTargetResult(identifier=piece, changed=True, detail=evidence.describe())

        client = self._client_for(action)
        task = await client.await_task(node, upid)
        log = await client.task_log(node, upid)
        tail = tuple(log[-EVIDENCE_LOG_LINES:])
        evidence = TaskEvidence(
            upid=upid,
            exit_status=task.exit_status or task.status,
            succeeded=task.succeeded,
            log=tail,
        )
        self.evidence[piece] = evidence
        if not task.succeeded:
            raise HypervisorTaskFailed(action.capability, str(action.target), task, tail)
        return SubTargetResult(identifier=piece, changed=True, detail=evidence.describe())


# --- The writers, one per capability ------------------------------------------


async def _start(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Start the guest the action names."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).start_guest(node, vmid, kind=kind)


async def _shutdown(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Ask the guest's own operating system to shut down, never forcing it."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).shutdown_guest(
        node,
        vmid,
        kind=kind,
        timeout_seconds=int(
            action.arguments.get("timeout_seconds", GUEST_SHUTDOWN_TIMEOUT_SECONDS)
        ),
        # Never. Escalating to a hard stop is a separate capability with a
        # separate class, and passing this would perform it under this name.
        force_stop=False,
    )


async def _reboot(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Reboot the guest through its own operating system."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).reboot_guest(
        node,
        vmid,
        kind=kind,
        timeout_seconds=int(
            action.arguments.get("timeout_seconds", GUEST_SHUTDOWN_TIMEOUT_SECONDS)
        ),
    )


async def _stop(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Stop the guest immediately."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).stop_guest(node, vmid, kind=kind)


async def _suspend(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Suspend the guest, writing its memory image out."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).suspend_guest(node, vmid, kind=kind)


async def _resume(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Resume the guest from its memory image."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).resume_guest(node, vmid, kind=kind)


async def _unlock(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Clear the guest's lock, or put one back when the action names it.

    One writer for both directions, because the rollback of an unlock is
    replayed through this same capability with the recorded lock in its
    arguments — and a second writer would be a second chance to spell the
    configuration key differently.
    """
    node, vmid, kind = _guest_of(action)
    restored = str(action.arguments.get("lock", ""))
    client = plane._client_for(action)
    if restored:
        return await client.set_guest_lock(node, vmid, kind=kind, lock=restored)
    return await client.clear_guest_lock(node, vmid, kind=kind)


async def _migrate(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Move the guest to the target node, online and only online."""
    node, vmid, kind = _guest_of(action)
    return await plane._client_for(action).migrate_guest(
        node,
        vmid,
        kind=kind,
        target=str(action.arguments.get("target", "")),
        # Always. An offline migration is refused by the precondition rather
        # than performed here, so this parameter has one correct value.
        online=True,
    )


async def _relocate(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Change what the high-availability manager holds about one resource."""
    return await plane._client_for(action).set_ha_state(
        str(action.arguments.get("sid", "")),
        group=str(action.arguments.get("group", "")),
        state=str(action.arguments.get("state", "")),
    )


async def _backup(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Run one guest's backup now."""
    node, vmid, _ = _guest_of(action)
    return await plane._client_for(action).run_backup(
        node,
        vmid=vmid,
        storage=str(action.arguments.get("storage", "")),
    )


async def _replicate(plane: ProxmoxControlPlane, action: RemediationAction) -> str:
    """Run one replication job now, under the rate limit the action carries."""
    node = str(action.arguments.get("node", ""))
    return await plane._client_for(action).run_replication(
        node,
        job_id=str(action.arguments.get("job_id", "")),
        rate_limit_mbps=int(action.arguments.get("rate_limit_mbps", plane.rate_limit_mbps)),
    )


#: Which client call each capability makes. A map rather than a chain of
#: branches, so a capability registered without a writer fails loudly at the
#: point of the write instead of silently doing nothing.
_WRITERS: Final[dict[str, Any]] = {
    "proxmox_start_guest": _start,
    "proxmox_shutdown_guest": _shutdown,
    "proxmox_reboot_guest": _reboot,
    "proxmox_stop_guest": _stop,
    "proxmox_suspend_guest": _suspend,
    "proxmox_resume_guest": _resume,
    "proxmox_unlock_guest": _unlock,
    "proxmox_migrate_guest": _migrate,
    "proxmox_ha_relocate": _relocate,
    "proxmox_retry_backup": _backup,
    "proxmox_resync_replication": _replicate,
}


# --- Reading an action --------------------------------------------------------


def _guest_of(action: RemediationAction) -> tuple[str, int, str]:
    """Return the node, number and kind a guest action names.

    From the arguments rather than from the target string. A hypervisor
    addresses a guest by three facts, and reconstructing them from
    ``name@environment`` would be a naming convention standing in for all three.
    """
    node = str(action.arguments.get("node", ""))
    kind = str(action.arguments.get("kind", ""))
    raw = action.arguments.get("vmid", 0)
    vmid = int(raw) if isinstance(raw, int | str) and str(raw).isdigit() else 0
    if not node or not kind or not vmid:
        raise ValueError(
            f"{action.capability} needs the node, the guest number and the guest kind, and "
            f"was given {action.arguments!r}. A write that guessed any of the three would "
            f"reach a guest with the same number and a different identity."
        )
    return node, vmid, kind


def _piece(action: RemediationAction) -> str:
    """Return the name of the single piece a non-storage action acts on."""
    if "sid" in action.arguments:
        return str(action.arguments["sid"])
    if "job_id" in action.arguments:
        return str(action.arguments["job_id"])
    return f"{action.arguments.get('kind', 'guest')}/{action.arguments.get('vmid', '?')}"


def _named_volumes(action: RemediationAction) -> tuple[str, ...]:
    """Return the volumes an action names, whether it names one or a list.

    A list goes through ``items_of``, which refuses anything that is a rule for
    choosing what to delete rather than a thing to delete. That check lives on
    the path to the deletion rather than only where the action was built,
    because this is the last point at which "the oldest three" can be stopped.
    """
    raw = action.arguments.get("items")
    if isinstance(raw, list | tuple):
        named = [str(entry) for entry in raw if str(entry).strip()]
        return items_of(named) if named else ()
    single = str(action.arguments.get("volume", "")).strip()
    return (single,) if single else ()


def _datastores_of(configuration: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the datastores a guest's configured disks live on."""
    found: set[str] = set()
    for key, raw in configuration.items():
        name = str(key)
        if not name.startswith(("scsi", "virtio", "ide", "sata", "rootfs", "mp")):
            continue
        value = str(raw)
        if ":" in value:
            found.add(value.split(":", 1)[0])
    return tuple(sorted(found))


def _seconds_until(schedule: str, now: int) -> int | None:
    """Return how many seconds until ``schedule``'s next run, or ``None``.

    Proxmox schedules are systemd calendar events, and only the plain
    ``HH:MM`` form is interpreted here. Anything richer returns ``None``, which
    makes the collision check say "nothing scheduled" rather than compute a
    wrong answer from a grammar this does not implement — and the richer forms
    are why an operator can still refuse the retry themselves.
    """
    hours, separator, minutes = schedule.strip().partition(":")
    if not separator or not hours.isdigit() or not minutes.isdigit():
        return None
    seconds_of_day = now % 86_400
    due = int(hours) * 3600 + int(minutes) * 60
    ahead = due - seconds_of_day
    return ahead if ahead >= 0 else ahead + 86_400


__all__ = [
    "EVIDENCE_LOG_LINES",
    "HypervisorTaskFailed",
    "ProxmoxControlPlane",
    "TaskEvidence",
]
