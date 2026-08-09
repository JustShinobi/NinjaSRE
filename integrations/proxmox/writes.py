"""The Proxmox writes, separate from the reads, and enumerated.

``ProxmoxClient`` is deliberately read-only: every method on it is a ``GET``, and
its docstring says so, because a write sitting among eighty reads is one typo
away from being called by something that thought it was reading. This subclass is
where the writes live, so the separation survives contact with a package that
needs both — a precondition is a read taken immediately before a write, and the
two have to come from one client or they are two different pictures.

**The endpoints are a declared list.** ``WRITE_ENDPOINTS`` is every path this
class may reach, as templates. It exists so a test can sweep the whole surface
and assert that nothing here fences a node, forces quorum, alters corosync,
restarts a node's own services, or writes a node's network configuration —
against the list rather than against somebody's memory of what was added.

**A write returns a task identifier, not a result.** Proxmox performs almost
everything asynchronously and answers with a UPID. The call returning 200 means
the task was *accepted*; whether it worked is the task's own outcome, read back
through ``await_task``, and conflating the two is the specific failure this
package is written to avoid.

**Nothing here holds a credential.** Like every client in this tree, it carries a
tenant-scoped context and reaches the vendor through the proxy, which injects the
secret at the network edge.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations.proxmox.client import GUEST_KINDS, ProxmoxClient
from integrations.proxmox.schema import INTEGRATION, base_url

#: How Proxmox is asked to delete a lock from a guest's configuration. The API
#: takes the *name of the property to remove* rather than an empty value, and an
#: empty value would be a lock called "".
LOCK_PROPERTY: Final = "lock"

#: Every path this client may write, as a template. One list, so the prohibition
#: sweep reads a declaration rather than the method bodies.
WRITE_ENDPOINTS: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/start"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/shutdown"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/reboot"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/stop"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/suspend"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/status/resume"),
    ("PUT", "/nodes/{node}/{kind}/{vmid}/config"),
    ("POST", "/nodes/{node}/{kind}/{vmid}/migrate"),
    ("PUT", "/cluster/ha/resources/{sid}"),
    ("DELETE", "/nodes/{node}/storage/{datastore}/content/{volume}"),
    ("POST", "/nodes/{node}/vzdump"),
    ("POST", "/nodes/{node}/replication/{job}/schedule_now"),
)


class ProxmoxWriteClient(ProxmoxClient):
    """Proxmox VE writes, each returning the task identifier Proxmox gave it."""

    __slots__ = ()

    # -- Guest lifecycle ------------------------------------------------------

    async def start_guest(self, node: str, vmid: int, *, kind: str) -> str:
        """Start a guest, and return the task identifier that will say whether it did."""
        return await self._task(f"{_guest(node, vmid, kind)}/status/start")

    async def shutdown_guest(
        self,
        node: str,
        vmid: int,
        *,
        kind: str,
        timeout_seconds: int,
        force_stop: bool = False,
    ) -> str:
        """Ask the guest's own operating system to shut down, and return the task.

        ``force_stop`` is Proxmox's own escalation and is passed explicitly rather
        than defaulted on: a graceful shutdown that silently becomes a hard stop
        after a timeout nobody declared is the escalation this feature exists to
        make visible.
        """
        return await self._task(
            f"{_guest(node, vmid, kind)}/status/shutdown",
            params={"timeout": str(timeout_seconds), "forceStop": "1" if force_stop else "0"},
        )

    async def reboot_guest(self, node: str, vmid: int, *, kind: str, timeout_seconds: int) -> str:
        """Reboot a guest through its own operating system, and return the task."""
        return await self._task(
            f"{_guest(node, vmid, kind)}/status/reboot",
            params={"timeout": str(timeout_seconds)},
        )

    async def stop_guest(self, node: str, vmid: int, *, kind: str) -> str:
        """Stop a guest immediately, and return the task.

        The hardware equivalent of pulling the power: nothing inside the guest is
        told, and anything it had not written is gone.
        """
        return await self._task(f"{_guest(node, vmid, kind)}/status/stop")

    async def suspend_guest(self, node: str, vmid: int, *, kind: str) -> str:
        """Suspend a guest, writing its memory image out, and return the task."""
        return await self._task(f"{_guest(node, vmid, kind)}/status/suspend")

    async def resume_guest(self, node: str, vmid: int, *, kind: str) -> str:
        """Resume a suspended guest, and return the task."""
        return await self._task(f"{_guest(node, vmid, kind)}/status/resume")

    async def clear_guest_lock(self, node: str, vmid: int, *, kind: str) -> str:
        """Remove the lock from a guest's configuration, and return the empty task.

        Synchronous on Proxmox's side — it is a configuration edit rather than an
        operation — so there is no identifier to poll and the empty string is the
        honest answer rather than a fabricated one.
        """
        await self._write(
            "PUT",
            f"{_guest(node, vmid, kind)}/config",
            params={"delete": LOCK_PROPERTY},
        )
        return ""

    async def set_guest_lock(self, node: str, vmid: int, *, kind: str, lock: str) -> str:
        """Write a lock back onto a guest's configuration, and return the empty task.

        What the unlock's rollback runs. A lock that was cleared in error is put
        back by name, which is why the previous value is recorded before it goes.
        """
        await self._write(
            "PUT",
            f"{_guest(node, vmid, kind)}/config",
            params={LOCK_PROPERTY: lock},
        )
        return ""

    # -- Movement -------------------------------------------------------------

    async def migrate_guest(
        self,
        node: str,
        vmid: int,
        *,
        kind: str,
        target: str,
        online: bool,
    ) -> str:
        """Move a guest to ``target``, and return the task.

        ``online`` is required rather than defaulted. An offline migration stops
        the guest, and a parameter that defaulted either way would be the place
        that decision got made by nobody.
        """
        return await self._task(
            f"{_guest(node, vmid, kind)}/migrate",
            params={"target": target, "online": "1" if online else "0"},
        )

    async def set_ha_state(self, sid: str, *, group: str = "", state: str = "") -> str:
        """Change one HA resource's requested state or group, and return the empty task.

        Proxmox applies the change to the manager's own configuration and the
        manager acts on it on its next round, so there is no task identifier here
        either — what happens next is read from the HA status.
        """
        parameters = {name: value for name, value in (("group", group), ("state", state)) if value}
        if not parameters:
            raise ValueError(
                "changing an HA resource needs the group or the state it should hold; a call "
                "that named neither would write nothing and report that it had"
            )
        await self._write("PUT", f"/cluster/ha/resources/{sid}", params=parameters)
        return ""

    # -- Storage --------------------------------------------------------------

    async def delete_volume(self, node: str, *, datastore: str, volume: str) -> str:
        """Delete one volume from a datastore, and return the task.

        ``volume`` is the whole volume identifier Proxmox reports —
        ``store:backup/vzdump-lxc-100-….tar.zst`` — and it is passed unparsed,
        because a caller that had to reassemble it is a caller that could
        assemble a different one.
        """
        return await self._task(
            f"/nodes/{node}/storage/{datastore}/content/{volume}",
            method="DELETE",
        )

    # -- Backups and replication ----------------------------------------------

    async def run_backup(
        self,
        node: str,
        *,
        vmid: int,
        storage: str,
        mode: str = "snapshot",
    ) -> str:
        """Run one guest's backup now, and return the task."""
        return await self._task(
            f"/nodes/{node}/vzdump",
            params={"vmid": str(vmid), "storage": storage, "mode": mode},
        )

    async def run_replication(self, node: str, *, job_id: str, rate_limit_mbps: int) -> str:
        """Run a replication job now under a rate limit, and return the task.

        The limit is required. Corosync shares the link a resync saturates, and a
        cluster that loses its membership layer to a storage sync has traded a
        lagging replica for an unquorate cluster.
        """
        return await self._task(
            f"/nodes/{node}/replication/{job_id}/schedule_now",
            params={"rate": str(rate_limit_mbps)},
        )

    # -- the one write path ---------------------------------------------------

    async def _task(
        self,
        path: str,
        *,
        method: str = "POST",
        params: Mapping[str, str] | None = None,
    ) -> str:
        """Return the task identifier a write was accepted with.

        Raises when Proxmox accepted the call and answered with something that is
        not a task identifier. A caller that treated an empty answer as a task
        would poll a task that does not exist and report the action as still
        running for ever.
        """
        answer = await self._write(method, path, params=params)
        if not isinstance(answer, str) or not answer.startswith("UPID:"):
            raise IntegrationError(
                f"{INTEGRATION} accepted {method} {path} and answered {answer!r}, which is not "
                f"a task identifier. Whether the operation happened cannot be established from "
                f"this, and reporting it as done would be reporting the request rather than "
                f"the result.",
                integration=INTEGRATION,
                reason=IntegrationErrorReason.UPSTREAM_ERROR,
            )
        return answer

    async def _write(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Make one write against the endpoint that is answering, and unwrap the envelope.

        No failover. A read may be retried against the next node in the ring
        because reading twice is free; a write may not, because the first attempt
        may have landed and the second would be a second change nobody approved.
        """
        response = await self.request(
            method,
            f"{base_url(self.endpoints.current)}{path}",
            params=params,
        )
        answer = response.json()
        if not isinstance(answer, dict) or "data" not in answer:
            raise IntegrationError(
                f"{INTEGRATION} answered {method} {path} with a body that is not a Proxmox "
                f"envelope, so nothing here can tell whether the write was accepted.",
                integration=INTEGRATION,
                reason=IntegrationErrorReason.UPSTREAM_ERROR,
            )
        return answer["data"]


def _guest(node: str, vmid: int, kind: str) -> str:
    """Return the path prefix for one guest, refusing a kind Proxmox has no path for."""
    if kind not in GUEST_KINDS:
        raise ValueError(
            f"{kind!r} is not a Proxmox guest kind. Containers are {GUEST_KINDS[0]!r} and "
            f"virtual machines are {GUEST_KINDS[1]!r}; they have different endpoints, and a "
            f"write against the wrong one reaches a guest with the same number and a different "
            f"identity."
        )
    return f"/nodes/{node}/{kind}/{vmid}"


__all__ = [
    "LOCK_PROPERTY",
    "WRITE_ENDPOINTS",
    "ProxmoxWriteClient",
]
