"""The Proxmox VE API, over the proxy, holding no credential.

Written by hand for the same reason the Kubernetes client was. Every Proxmox
client library reads its own credential — from a constructor argument, a file, or
an environment variable — and that is the behaviour Article IV forbids and the
one thing about such a library that is never configurable. The surface an
investigation needs is a bounded set of REST paths, all of them below, and
writing them against the proxy transport is both smaller than the adaptation
would be and compliant by construction.

Four things about this client are Proxmox-specific and worth reading before the
methods.

**Every answer is wrapped.** Proxmox replies ``{"data": ...}`` to everything,
including errors. ``_read`` unwraps it once so that eighty call sites do not each
index into it, and an answer that is not that shape raises here rather than
somewhere inside a capability.

**A cluster has several addresses and this walks them.** ``EndpointRing`` decides
which node to talk to; a refused connection moves to the next, a 403 does not.
The property that matters is that reads keep working when the node named in the
configuration is the one that died.

**A node that is down is not a client failure.** Proxmox answers a cluster-wide
read normally while answering that node's own reads with a 595. Those reads
return an absent ``Reading`` naming what happened, and the cluster-wide view
still enumerates the node — which is what makes a down node's guests *stale*
rather than absent.

**Nothing here writes.** Every method is a ``GET``. Restarting a guest, migrating
one, or triggering a backup are remediations that need an approval and a rollback
plan, and putting one in this class would leave it one typo away from being
called by something that thought it was reading.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Self

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.pagination import EndpointPagination, PaginationStyle
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.proxmox.certificates import DEFAULT_TRUST, CertificateTrust
from integrations.proxmox.endpoints import EndpointRing
from integrations.proxmox.models import (
    BackupJob,
    ClusterConfiguration,
    ClusterStatus,
    Datastore,
    GuestStatus,
    HighAvailabilityState,
    NetworkInterface,
    NodeMembership,
    NodeStatus,
    PendingUpdate,
    PhysicalDisk,
    Reading,
    ReplicationJob,
    TaskRecord,
    ThinPool,
    ThinVolume,
    parse_upid,
)
from integrations.proxmox.schema import API_BASE, DEFAULT_HOST, INTEGRATION
from integrations.proxmox.schema import base_url as base_url_of
from platform.observability.logging import get_logger

#: The two guest kinds, spelled the way Proxmox spells them in its own paths.
#: A tuple rather than an enum because these strings *are* path segments, and a
#: value that has to be unwrapped before it can be used in a URL is a value that
#: will eventually be used without being unwrapped.
GUEST_KINDS: Final[tuple[str, ...]] = ("lxc", "qemu")

#: How many task records one call returns. A node in a backup window produces
#: them faster than anything reads them, and the recent ones are the ones that
#: explain the incident.
MAX_TASKS: Final = 100

#: How many lines of one task's log are read. A restore of a 900 GiB volume logs
#: without bound, and the alternative to a ceiling is a trace nobody can open.
MAX_TASK_LOG_LINES: Final = 500

#: How many times ``await_task`` asks before reporting a task still running.
#: Bounded in calls as well as in time, because a task that never finishes would
#: otherwise hold a worker for the whole of its time budget.
MAX_TASK_POLLS: Final = 10

#: Seconds between polls. Proxmox tasks that finish quickly finish in under one.
TASK_POLL_SECONDS: Final = 1.0

#: Proxmox's status for "the node that owns this endpoint is not answering". A
#: cluster with a node down answers cluster-wide reads normally and answers that
#: node's own reads with this, so it is a reading about the node rather than an
#: error about the request.
NODE_UNREACHABLE_STATUS: Final = 595

#: Proxmox pages exactly one endpoint, and it pages it by offset: the task list
#: takes ``start`` and ``limit`` and terminates on a short page. Everything else
#: answers in full, which is why one declaration covers the API.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="node_tasks",
        style=PaginationStyle.OFFSET,
        parameter="start",
        page_size_parameter="limit",
        page_size=MAX_TASKS,
    ),
)


logger = get_logger(__name__)


def _host_of(address: str) -> str:
    """Return the bare host an address names, or "" when it names none.

    The endpoint ring is a ring of *hosts* — failover walks node names — while
    the configured address is a URL. This is the one translation between them,
    and it is here rather than in the ring because the ring has no business
    knowing about schemes.
    """
    trimmed = address.strip()
    if not trimmed:
        return ""
    authority = trimmed.split("://", 1)[-1].split("/", 1)[0]
    if authority.startswith("["):
        return authority.partition("]")[0].lstrip("[")
    return authority.split(":", 1)[0]


def _api_root(address: str) -> str:
    """Return ``address`` with Proxmox's API prefix, added once.

    An operator types the address they sign in at. Every path in this client is
    relative to ``/api2/json``, and appending it here rather than asking for it
    is the difference between a working credential and a 404 that reads like a
    permissions problem.
    """
    trimmed = address.strip().rstrip("/")
    return trimmed if trimmed.endswith(API_BASE) else f"{trimmed}{API_BASE}"


class ProxmoxClient(IntegrationClient):
    """Proxmox VE reads, reached through the credential proxy and never around it."""

    integration = INTEGRATION

    __slots__ = ("_endpoints", "_trust")

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        endpoints: Sequence[str] = (),
        trust: CertificateTrust = DEFAULT_TRUST,
        base_url: str = "",
        retry: RetryPolicy | None = None,
    ) -> None:
        ring = EndpointRing.of(
            *(tuple(endpoints) or (_host_of(base_url) or DEFAULT_HOST,)), integration=INTEGRATION
        )
        super().__init__(
            transport=transport,
            context=context,
            base_url=_api_root(base_url) if base_url else base_url_of(ring.current),
            retry=retry,
        )
        self._endpoints = ring
        self._trust = trust

    @property
    def endpoints(self) -> EndpointRing:
        """Return the addresses this client will try, and which are answering."""
        return self._endpoints

    @property
    def trust(self) -> CertificateTrust:
        """Return what this deployment accepts from the endpoint's certificate."""
        return self._trust

    def for_team(self, team_id: str) -> Self:
        """Return a copy of this client configured with ``team_id`` in its request context."""
        if not team_id or team_id == self._context.team_id:
            return self
        return type(self)(
            transport=self._transport,
            context=RequestContext(
                org_id=self._context.org_id,
                team_id=team_id,
                capability=self._context.capability,
            ),
            endpoints=self._endpoints.hosts,
            trust=self._trust,
            base_url=self._base_url,
            retry=self._retry,
        )

    # -- the one read path ----------------------------------------------------

    async def read_response(
        self, path: str, *, params: Mapping[str, str] | None = None
    ) -> ClientResponse:
        """Return one endpoint's answer without interpreting the envelope.

        What a permission probe wants. A probe asks whether the call is
        *permitted*, not what came back, and insisting on a well-formed Proxmox
        envelope would turn a successful authorisation check into a parse error
        the moment a deployment put anything in front of its API.
        """

        async def fetch(host: str) -> ClientResponse:
            return await self.get(f"{base_url_of(host)}{path}", params=params)

        return await self._endpoints.attempt(fetch)

    async def _read(self, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        """Return the ``data`` a Proxmox endpoint answered with.

        Fails over between the configured addresses, unwraps the envelope once,
        and raises whatever the base client raised for anything failover cannot
        fix.
        """

        async def fetch(host: str) -> Any:
            response = await self.get(f"{base_url_of(host)}{path}", params=params)
            answer = response.json()
            if not isinstance(answer, dict) or "data" not in answer:
                raise IntegrationError(
                    f"{INTEGRATION} answered {path} with a body that is not a Proxmox "
                    f"envelope. Every endpoint replies {{'data': ...}}, so this is either "
                    f"a different service on that address or a proxy in the way.",
                    integration=INTEGRATION,
                    reason=IntegrationErrorReason.UPSTREAM_ERROR,
                )
            return answer["data"]

        return await self._endpoints.attempt(fetch)

    async def _read_node(
        self,
        node: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Reading[Any]:
        """Return a node-scoped reading, absent rather than raised when the node is down."""
        try:
            return Reading.of(await self._read(f"/nodes/{node}{path}", params=params))
        except IntegrationError as error:
            if error.status_code == NODE_UNREACHABLE_STATUS:
                return Reading.missing(
                    f"{node} did not answer: Proxmox returned {NODE_UNREACHABLE_STATUS}, which "
                    f"means the cluster is up and that node is not",
                    published_by=f"the {node} node itself",
                )
            raise

    async def ping(self) -> Any:
        """Read the API version — the cheapest authenticated call Proxmox offers."""
        return await self.get(f"{base_url_of(self._endpoints.current)}/version")

    async def version(self) -> Mapping[str, Any]:
        """Return the version, release and build of the node that answered."""
        return dict(await self._read("/version"))

    async def access_permissions(self) -> Mapping[str, Any]:
        """Return this token's effective privileges, by path.

        Proxmox answers with what the credential *actually* holds, privilege
        separation already applied — so a separated token and a full one are read
        the same way and neither needs a special case. It is also the reason
        verification here can name a missing privilege rather than inferring one
        from a probe that happened to fail.
        """
        return _record(await self._read("/access/permissions"))

    # -- Phase 2: the cluster -------------------------------------------------

    async def cluster_status(self) -> ClusterStatus:
        """Return quorum state, votes, and who is in the cluster.

        A cluster without quorum is a successful read of a bad state, not a
        failed read. Treating it as a connection failure would hide the single
        most important fact about a two-node cluster.
        """
        records = _records(await self._read("/cluster/status"))
        cluster = next((row for row in records if row.get("type") == "cluster"), None)
        quorum = next((row for row in records if row.get("type") == "quorum"), {})
        members = tuple(
            NodeMembership(
                name=str(row.get("name", "")),
                online=bool(row.get("online", 0)),
                node_id=int(row.get("nodeid", 0) or 0),
                address=str(row.get("ip", "")),
                local=bool(row.get("local", 0)),
            )
            for row in records
            if row.get("type") == "node"
        )

        if cluster is None:
            # A standalone installation. It has not lost quorum; it never had
            # one, and reporting it unquorate would be a critical finding about
            # an installation working exactly as intended.
            return ClusterStatus(
                name=members[0].name if members else "",
                members=members,
                is_clustered=False,
                quorate=all(member.online for member in members),
                expected_votes=len(members),
                total_votes=len([member for member in members if member.online]),
                quorum_required=1,
            )

        return ClusterStatus(
            name=str(cluster.get("name", "")),
            members=members,
            quorate=bool(quorum.get("quorate", cluster.get("quorate", 0))),
            expected_votes=int(quorum.get("expected_votes", 0) or 0),
            total_votes=int(quorum.get("total_votes", 0) or 0),
            quorum_required=int(quorum.get("quorum", 0) or 0),
            quorum_device=str(quorum.get("qdevice", "")),
            version=str(cluster.get("version", "")),
        )

    async def cluster_resources(self) -> tuple[Mapping[str, Any], ...]:
        """Return every node, guest and datastore the cluster knows about.

        One call for the whole estate, which is why discovery prefers it: fifty
        guests times several per-guest reads is a call budget nobody has, and the
        per-guest reads belong to an investigation that already knows which guest.
        """
        return _records(await self._read("/cluster/resources"))

    async def cluster_configuration(self) -> ClusterConfiguration:
        """Return the corosync configuration, including the settings that are absent.

        ``two_node`` and ``wait_for_all`` are read as booleans that default to
        false, because their absence is the finding: a two-node cluster without
        either has a quorum margin of zero and does not say so anywhere else.
        """
        nodes = _records(await self._read("/cluster/config/nodes"))
        totem = _record(await self._read("/cluster/config/totem"))
        return ClusterConfiguration(
            cluster_name=str(totem.get("cluster_name", "")),
            config_version=str(totem.get("config_version", "")),
            transport=str(totem.get("transport", "")),
            secure_authentication=str(totem.get("secauth", "")).lower() == "on",
            nodes=nodes,
            two_node=_switch(totem.get("two_node")),
            wait_for_all=_switch(totem.get("wait_for_all")),
            last_man_standing=_switch(totem.get("last_man_standing")),
            has_quorum_device=bool(totem.get("device")),
            links=_declared_links(nodes),
        )

    async def _placement_rules(self) -> tuple[tuple[Mapping[str, Any], ...], int]:
        """Return HA placement rules and what asking for them cost.

        The cost is returned rather than assumed because it varies: a cluster
        that serves the newer endpoint costs one call, and one part-way through
        the upgrade costs two. A sweep works to a declared budget, so it needs
        the number rather than an estimate.
        """
        spent = 0
        for path in ("/cluster/ha/rules", "/cluster/ha/groups"):
            spent += 1
            try:
                found = _records(await self._read(path))
            except IntegrationError as retired:
                logger.info(
                    "proxmox.ha_endpoint_unavailable",
                    path=path,
                    reason=str(retired.reason),
                )
                continue
            if found:
                return found, spent
        return (), spent

    async def cluster_log(self, *, limit: int = 100) -> tuple[Mapping[str, Any], ...]:
        """Return the most recent cluster log entries."""
        return _records(await self._read("/cluster/log", params={"max": str(limit)}))

    async def high_availability(self) -> HighAvailabilityState:
        """Return HA resources, groups or rules, manager status and fencing state.

        Proxmox VE 9 migrated HA groups to HA rules and soft-disabled the old
        endpoint rather than removing it — a cluster part-way through the
        upgrade still has groups, so the old path answers 500 with "ha groups
        have been migrated to rules". Both are asked for, newest first, and
        neither answering is an HA read with no placement rules rather than a
        failed one: this is one call in a sweep, and a retired endpoint must not
        take the estate down with it.
        """
        resources = _records(await self._read("/cluster/ha/resources"))
        groups, placement_calls = await self._placement_rules()
        current = _records(await self._read("/cluster/ha/status/current"))

        manager = next((row for row in current if row.get("type") == "master"), {})
        return HighAvailabilityState(
            resources=resources,
            groups=groups,
            services=tuple(row for row in current if row.get("type") == "service"),
            manager_node=str(manager.get("node", "")),
            manager_status=str(manager.get("status", "")),
            fencing_mode=str(manager.get("mode", "watchdog")),
            lrm_states={
                str(row.get("node", "")): str(row.get("status", ""))
                for row in current
                if row.get("type") == "lrm"
            },
            provider_calls=2 + placement_calls,
        )

    async def backup_jobs(self) -> tuple[BackupJob, ...]:
        """Return the cluster-wide vzdump job definitions.

        ``enabled`` is carried because a job that exists and is switched off is
        the most dangerous shape a backup has: every inventory of "is there a
        backup job for this guest" answers yes.
        """
        return tuple(
            BackupJob(
                job_id=str(row.get("id", "")),
                enabled=bool(int(row.get("enabled", 0) or 0)),
                schedule=str(row.get("schedule", "")),
                comment=str(row.get("comment", "")),
                storage=str(row.get("storage", "")),
                node=str(row.get("node", "")),
                covers_everything=bool(int(row.get("all", 0) or 0)),
                vmids=_vmids(row.get("vmid", "")),
                retention=str(row.get("prune-backups", "")),
            )
            for row in _records(await self._read("/cluster/backup"))
        )

    # -- Phase 3: nodes -------------------------------------------------------

    async def node_status(self, node: str) -> Reading[NodeStatus]:
        """Return one node's uptime, load, memory, root filesystem and versions."""
        reading = await self._read_node(node, "/status")
        if not reading.available:
            return Reading.missing(reading.unavailable_reason, published_by=reading.published_by)

        found = _record(reading.require())
        memory = _record(found.get("memory"))
        swap = _record(found.get("swap"))
        root = _record(found.get("rootfs"))
        loads = found.get("loadavg") or ["0"]
        return Reading.of(
            NodeStatus(
                node=node,
                uptime_seconds=int(found.get("uptime", 0) or 0),
                load_average=float(loads[0]),
                cpu_ratio=float(found.get("cpu", 0.0) or 0.0),
                cpu_count=int(_record(found.get("cpuinfo")).get("cpus", 0) or 0),
                memory_total_bytes=int(memory.get("total", 0) or 0),
                memory_used_bytes=int(memory.get("used", 0) or 0),
                swap_total_bytes=int(swap.get("total", 0) or 0),
                swap_used_bytes=int(swap.get("used", 0) or 0),
                root_total_bytes=int(root.get("total", 0) or 0),
                root_used_bytes=int(root.get("used", 0) or 0),
                kernel_version=str(found.get("kversion", "")),
                proxmox_version=_pve_version(str(found.get("pveversion", ""))),
            )
        )

    async def node_storage(self, node: str) -> tuple[Datastore, ...]:
        """Return the datastores this node can see, with their fill and status."""
        reading = await self._read_node(node, "/storage")
        return tuple(
            Datastore(
                name=str(row.get("storage", "")),
                node=node,
                storage_type=str(row.get("type", "")),
                status="available" if row.get("active", 0) else str(row.get("status", "unknown")),
                shared=bool(int(row.get("shared", 0) or 0)),
                total_bytes=int(row.get("total", 0) or 0),
                used_bytes=int(row.get("used", 0) or 0),
                content=tuple(str(row.get("content", "")).split(",")) if row.get("content") else (),
            )
            for row in _records(reading.or_else([]))
        )

    async def datastore_status(self, node: str, datastore: str) -> Reading[Datastore]:
        """Return one datastore's own status as the node reports it."""
        reading = await self._read_node(node, f"/storage/{datastore}/status")
        if not reading.available:
            return Reading.missing(reading.unavailable_reason)
        found = _record(reading.require())
        return Reading.of(
            Datastore(
                name=datastore,
                node=node,
                storage_type=str(found.get("type", "")),
                status="available" if found.get("active", 0) else "unknown",
                shared=bool(int(found.get("shared", 0) or 0)),
                total_bytes=int(found.get("total", 0) or 0),
                used_bytes=int(found.get("used", 0) or 0),
            )
        )

    async def storage_configuration(self) -> tuple[Mapping[str, Any], ...]:
        """Return the cluster-wide datastore definitions, with their node restrictions.

        A different question from ``node_storage``, which says what one node can
        currently reach. This says what the cluster *declares*, including the
        ``nodes`` field that restricts a datastore to a subset — and a guest
        cannot move to a node its disk's datastore is not declared on, however
        healthy both nodes are.
        """
        return _records(await self._read("/storage"))

    async def datastore_contents(
        self, node: str, datastore: str, *, content: str = ""
    ) -> tuple[Mapping[str, Any], ...]:
        """Return what a datastore is holding — images, backups, ISO files."""
        params = {"content": content} if content else None
        reading = await self._read_node(node, f"/storage/{datastore}/content", params=params)
        return _records(reading.or_else([]))

    async def node_disks(self, node: str) -> tuple[PhysicalDisk, ...]:
        """Return the physical disks in a node, with the verdict SMART gives."""
        reading = await self._read_node(node, "/disks/list")
        return tuple(
            PhysicalDisk(
                device=str(row.get("devpath", "")),
                size_bytes=int(row.get("size", 0) or 0),
                model=str(row.get("model", "")),
                serial=str(row.get("serial", "")),
                disk_type=str(row.get("type", "")),
                smart_health=str(row.get("health", "")),
                wearout=str(row.get("wearout", "")),
                used_for=str(row.get("used", "")),
            )
            for row in _records(reading.or_else([]))
        )

    async def disk_smart(self, node: str, device: str) -> Reading[Mapping[str, Any]]:
        """Return one disk's SMART report: the verdict and the attributes behind it.

        ``node_disks`` carries the verdict, which is a summary the firmware makes
        and keeps saying ``PASSED`` while the attributes that predict failure
        climb. Reallocated sectors and pending sectors are the reading; the
        verdict is the reading's opinion of itself.

        Absent rather than empty when the drive has no SMART — a USB enclosure,
        a virtual disk — because "we asked and there is nothing" and "nobody is
        watching this disk" are the same sentence and only one of them is true.
        """
        reading = await self._read_node(node, "/disks/smart", params={"disk": device})
        if not reading.available:
            return Reading.missing(
                f"SMART for {device} on {node} could not be read: {reading.unavailable_reason}",
                published_by="the drive's own firmware, through smartctl",
            )
        found = _record(reading.require())
        if not found:
            return Reading.missing(
                f"{device} on {node} reported no SMART data, so nothing about this disk is "
                f"being watched — which is not the same as the disk being healthy",
                published_by="the drive's own firmware, through smartctl",
            )
        return Reading.of(found)

    async def thin_pools(self, node: str) -> tuple[ThinPool, ...]:
        """Return the LVM-thin pools on a node, data and metadata separately.

        LVM-thin is the primary storage technology in the reference cluster and
        the two percentages fail differently: a pool that exhausts its metadata
        stops accepting writes while its data figure still looks comfortable.
        """
        reading = await self._read_node(node, "/disks/lvmthin")
        return tuple(
            ThinPool(
                name=str(row.get("lv", "")),
                volume_group=str(row.get("vg", "")),
                size_bytes=int(row.get("lv_size", 0) or 0),
                data_percent=float(row.get("data_percent", 0.0) or 0.0),
                metadata_percent=float(row.get("metadata_percent", 0.0) or 0.0),
                state=str(row.get("lv_state", "")),
            )
            for row in _records(reading.or_else([]))
        )

    async def thin_volumes(self, node: str) -> tuple[ThinVolume, ...]:
        """Return each guest's own volume and how full it is.

        The reading a datastore-level threshold cannot make. A datastore at 84%
        while the volume inside it is at 99.6% is one guest about to see write
        failures and one number that says everything is fine.
        """
        reading = await self._read_node(node, "/disks/lvm")
        return tuple(
            ThinVolume(
                name=str(row.get("lv", "")),
                volume_group=str(row.get("vg", "")),
                size_bytes=int(row.get("lv_size", 0) or 0),
                data_percent=float(row.get("data_percent", 0.0) or 0.0),
                vmid=_vmid_of(str(row.get("lv", ""))),
            )
            for row in _records(reading.or_else([]))
        )

    async def zfs_pools(self, node: str) -> Reading[tuple[Mapping[str, Any], ...]]:
        """Return the ZFS pools on a node, where there are any.

        A node without ZFS is the ordinary case rather than a read failure —
        neither reference node has a pool — so an empty answer is a present
        reading of nothing, and only an unreachable node is an absent one.
        """
        reading = await self._read_node(node, "/disks/zfs")
        if not reading.available:
            return Reading.missing(reading.unavailable_reason)
        return Reading.of(_records(reading.require()))

    async def zfs_pool_detail(self, node: str, pool: str) -> Reading[Mapping[str, Any]]:
        """Return one ZFS pool's device tree, scrub line and error summary.

        The pool listing carries a health word; this carries the reason for it.
        A pool that says ``ONLINE`` while one leaf device is accumulating
        checksum errors is a pool one more error away from saying ``DEGRADED``,
        and only the device tree says so.
        """
        reading = await self._read_node(node, f"/disks/zfs/{pool}")
        if not reading.available:
            return Reading.missing(
                f"the pool {pool!r} on {node} could not be read: {reading.unavailable_reason}",
                published_by=f"zpool on {node}",
            )
        found = _record(reading.require())
        if not found:
            return Reading.missing(
                f"{node} has no ZFS pool called {pool!r}, so nothing was read about it",
                published_by=f"zpool on {node}",
            )
        return Reading.of(found)

    async def node_tasks(
        self,
        node: str,
        *,
        limit: int = MAX_TASKS,
        start: int = 0,
    ) -> tuple[TaskRecord, ...]:
        """Return a node's recent task history, newest first."""
        reading = await self._read_node(
            node,
            "/tasks",
            params={"limit": str(min(limit, MAX_TASKS)), "start": str(start)},
        )
        return tuple(_task(row) for row in _records(reading.or_else([])))

    async def replication_jobs(self, node: str) -> tuple[ReplicationJob, ...]:
        """Return a node's replication jobs and how the last run went.

        None at all is a reading, not an absence: guests on node-local storage
        with no replication mean a node loss is unrecoverable inside the cluster.
        """
        reading = await self._read_node(node, "/replication")
        return tuple(
            ReplicationJob(
                job_id=str(row.get("id", "")),
                source=str(row.get("source", "")),
                target=str(row.get("target", "")),
                guest=int(row.get("guest", 0) or 0),
                enabled=not int(row.get("disable", 0) or 0),
                last_sync=int(row.get("last_sync", 0) or 0),
                duration_seconds=float(row.get("duration", 0.0) or 0.0),
                fail_count=int(row.get("fail_count", 0) or 0),
                error=str(row.get("error", "")),
            )
            for row in _records(reading.or_else([]))
        )

    async def node_certificates(self, node: str) -> tuple[Mapping[str, Any], ...]:
        """Return the certificates a node serves, with their expiry."""
        reading = await self._read_node(node, "/certificates/info")
        return _records(reading.or_else([]))

    async def pending_updates(self, node: str) -> tuple[PendingUpdate, ...]:
        """Return the packages a node has available but has not installed."""
        reading = await self._read_node(node, "/apt/update")
        return tuple(
            PendingUpdate(
                package=str(row.get("Package", "")),
                version=str(row.get("Version", "")),
                priority=str(row.get("Priority", "")),
            )
            for row in _records(reading.or_else([]))
        )

    async def node_network(self, node: str) -> tuple[NetworkInterface, ...]:
        """Return a node's interface configuration, bridges included.

        Everything on a Proxmox node depends on ``vmbr0`` and nothing else
        watches it: a bridge that failed to build takes corosync, the cluster
        filesystem, and every guest's network with it.
        """
        reading = await self._read_node(node, "/network")
        return tuple(
            NetworkInterface(
                name=str(row.get("iface", "")),
                interface_type=str(row.get("type", "")),
                active=bool(int(row.get("active", 0) or 0)),
                autostart=bool(int(row.get("autostart", 0) or 0)),
                address=str(row.get("cidr", row.get("address", ""))),
                ports=tuple(str(row.get("bridge_ports", "")).split())
                if row.get("bridge_ports")
                else (),
            )
            for row in _records(reading.or_else([]))
        )

    async def node_time(self, node: str) -> Mapping[str, Any]:
        """Return a node's clock and time zone."""
        reading = await self._read_node(node, "/time")
        return _record(reading.or_else({}))

    # -- Phase 4: guests ------------------------------------------------------

    async def guest_status(self, node: str, vmid: int, *, kind: str) -> GuestStatus:
        """Return one guest's current state, lock, and HA membership."""
        found = _record(await self._read(f"{_guest_path(node, vmid, kind)}/status/current"))
        return GuestStatus(
            vmid=vmid,
            kind=kind,
            node=node,
            status=str(found.get("status", "")),
            name=str(found.get("name", "")),
            cpus=int(found.get("cpus", 0) or 0),
            memory_bytes=int(found.get("maxmem", 0) or 0),
            memory_used_bytes=int(found.get("mem", 0) or 0),
            disk_bytes=int(found.get("maxdisk", 0) or 0),
            disk_used_bytes=int(found.get("disk", 0) or 0),
            uptime_seconds=int(found.get("uptime", 0) or 0),
            lock=str(found.get("lock", "")),
            ha_managed=bool(int(_record(found.get("ha")).get("managed", 0) or 0)),
            template=bool(int(found.get("template", 0) or 0)),
            agent_declared=bool(int(found.get("agent", 0) or 0)),
        )

    async def guest_configuration(self, node: str, vmid: int, *, kind: str) -> Mapping[str, Any]:
        """Return one guest's configuration, exactly as Proxmox holds it.

        Unmasked on purpose. Guest configuration routinely contains a cloud-init
        password or an SSH key, and masking belongs at the boundary where the
        value is stored or shown rather than in the read — a client that
        redacted would leave a capability unable to say *which* key is set.
        ``redaction.masked_configuration`` is what discovery and the tools call.
        """
        return _record(await self._read(f"{_guest_path(node, vmid, kind)}/config"))

    async def guest_snapshots(
        self, node: str, vmid: int, *, kind: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Return the snapshots a guest has."""
        return _records(await self._read(f"{_guest_path(node, vmid, kind)}/snapshot"))

    async def guest_pending(
        self, node: str, vmid: int, *, kind: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Return the configuration changes waiting for the guest to restart."""
        return _records(await self._read(f"{_guest_path(node, vmid, kind)}/pending"))

    async def guest_tasks(self, node: str, vmid: int, *, kind: str) -> tuple[TaskRecord, ...]:
        """Return a guest's own recent task history, newest first.

        Read from the node's task log narrowed to this guest, because a guest
        has no task endpoint of its own. ``/nodes/{node}/{kind}/{vmid}/status/
        tasks`` looks like it should be one and a live hypervisor answers ``No
        'get' handler defined`` — a 501 that arrives as a vendor failure and
        costs the caller its turn. It cost two capabilities theirs on a real
        incident, where the answer they were after, a manual stop and who made
        it, was one path away the whole time.

        Narrowed on both sides. Proxmox filters when it is given ``vmid``, and
        the result is filtered again here, so a deployment whose Proxmox ignores
        the parameter gets this guest's tasks rather than the node's.

        ``kind`` is still validated even though the path no longer carries it: a
        caller naming something that is neither a container nor a virtual
        machine has a bug, and a filtered list that happens to be empty would
        hide it.
        """
        _guest_path(node, vmid, kind)
        reading = await self._read_node(
            node,
            "/tasks",
            params={"vmid": str(vmid), "limit": str(MAX_TASKS), "start": "0"},
        )
        tasks = (_task(row) for row in _records(reading.or_else([])))
        return tuple(task for task in tasks if task.vmid == vmid)

    async def guest_agent_filesystems(
        self, node: str, vmid: int
    ) -> Reading[tuple[Mapping[str, Any], ...]]:
        """Return what the guest's own agent says about its filesystems.

        An agent that is not installed, not running, or not answering produces an
        absent reading naming the agent. That distinction is FR-020's whole
        point: "the agent did not answer" and "the guest is unhealthy" are
        different sentences, and only one of them is about the guest.
        """
        try:
            answer = _record(await self._read(f"/nodes/{node}/qemu/{vmid}/agent/get-fsinfo"))
        except IntegrationError as error:
            said = error.status_code or "nothing"
            return Reading.missing(
                f"the QEMU guest agent on {vmid} did not answer, and Proxmox said {said}. "
                f"That is a fact about the agent, not about the guest.",
                published_by="qemu-guest-agent, inside the guest",
            )
        return Reading.of(_records(answer.get("result")))

    # -- Phase 5: backups -----------------------------------------------------

    async def backup_outcomes(self, node: str) -> tuple[TaskRecord, ...]:
        """Return the backup tasks a node has run, newest first."""
        return tuple(task for task in await self.node_tasks(node) if task.task_type == "vzdump")

    async def last_successful_backup(self, node: str) -> Mapping[int, TaskRecord]:
        """Return each guest's most recent *successful* backup on this node.

        Keyed by guest, and a guest whose every attempt failed is simply absent —
        which is the answer, and is different from a guest with a backup that is
        merely old.
        """
        latest: dict[int, TaskRecord] = {}
        for task in await self.backup_outcomes(node):
            if not task.succeeded or task.vmid == 0:
                continue
            held = latest.get(task.vmid)
            if held is None or task.started_at > held.started_at:
                latest[task.vmid] = task
        return latest

    # -- Phase 6: tasks -------------------------------------------------------

    async def task_status(self, node: str, upid: str) -> TaskRecord:
        """Return one task's current state, by the identifier Proxmox gave it."""
        found = _record(await self._read(f"/nodes/{node}/tasks/{upid}/status"))
        return _task({**parse_upid(upid), **found, "upid": upid})

    async def task_log(
        self, node: str, upid: str, *, limit: int = MAX_TASK_LOG_LINES
    ) -> tuple[str, ...]:
        """Return up to ``limit`` lines of one task's log.

        Bounded on this side as well as in the request. A restore of a very large
        volume logs without limit, and a vendor that ignored the parameter would
        otherwise put the whole of it into a trace.
        """
        capped = min(limit, MAX_TASK_LOG_LINES)
        records = _records(
            await self._read(
                f"/nodes/{node}/tasks/{upid}/log",
                params={"limit": str(capped), "start": "0"},
            )
        )
        return tuple(str(row.get("t", "")) for row in records[:capped])

    async def await_task(
        self,
        node: str,
        upid: str,
        *,
        max_polls: int = MAX_TASK_POLLS,
        delay_seconds: float = TASK_POLL_SECONDS,
    ) -> TaskRecord:
        """Poll a task until it finishes or the bound is reached, and say which.

        Bounded in calls and in time, and it reports a task *still running*
        rather than waiting: an operation that outlives the poll budget is a
        fact worth reporting, and blocking indefinitely on one would hold the
        worker an investigation is running in.
        """
        bound = max(1, min(max_polls, MAX_TASK_POLLS))
        record = TaskRecord(upid=upid)
        for attempt in range(1, bound + 1):
            record = await self.task_status(node, upid)
            record = _with_polls(record, attempt)
            if record.finished:
                return record
            if attempt < bound and delay_seconds > 0:
                await _pause(delay_seconds)
        return record


# --- Reading Proxmox's answers ------------------------------------------------


def _records(payload: Any) -> tuple[Mapping[str, Any], ...]:
    """Return ``payload`` as a tuple of records, whatever shape it arrived in.

    Proxmox answers a list endpoint with a list and occasionally with an object
    keyed by name. Both are records; a caller that had to know which would break
    on the endpoint that changed.
    """
    if isinstance(payload, list):
        return tuple(row for row in payload if isinstance(row, dict))
    if isinstance(payload, dict):
        return tuple(value for value in payload.values() if isinstance(value, dict))
    return ()


def _record(payload: Any) -> Mapping[str, Any]:
    """Return ``payload`` as one record, or an empty one."""
    return payload if isinstance(payload, dict) else {}


def _guest_path(node: str, vmid: int, kind: str) -> str:
    """Return the path prefix for one guest, refusing a kind Proxmox has no path for."""
    if kind not in GUEST_KINDS:
        raise ValueError(
            f"{kind!r} is not a Proxmox guest kind. Containers are {GUEST_KINDS[0]!r} and "
            f"virtual machines are {GUEST_KINDS[1]!r}; they have different endpoints and "
            f"different configuration, which is why they are not one word."
        )
    return f"/nodes/{node}/{kind}/{vmid}"


def _task(row: Mapping[str, Any]) -> TaskRecord:
    """Return one task record from whichever endpoint reported it."""
    upid = str(row.get("upid", ""))
    packed = parse_upid(upid)
    return TaskRecord(
        upid=upid,
        task_type=str(row.get("type", packed.get("type", ""))),
        status=str(row.get("status", "")),
        exit_status=str(row.get("exitstatus", "")),
        node=str(row.get("node", packed.get("node", ""))),
        user=str(row.get("user", packed.get("user", ""))),
        vmid=_guest_of(row.get("id", packed.get("id", 0))),
        started_at=int(row.get("starttime", packed.get("starttime", 0)) or 0),
        ended_at=int(row.get("endtime", 0) or 0),
    )


def _guest_of(value: Any) -> int:
    """Return the guest a task is about, or nought when it is about no guest.

    A task's ``id`` means whatever its type means: the vmid for a guest
    operation, the datastore for a backup, the node's own name for anything
    about the node. Reading all three as an integer raised ``ValueError`` on
    the first ``vzdump`` or ``srvstop`` in the log — and because the parse ran
    over the whole list, one such row took every task with it.

    That cost three capabilities at once: the guest's task history, backup
    coverage and backup failures all read this log, so on a cluster that takes
    backups they failed together and kept failing. It is what stopped an
    investigation from ever learning that a container had been shut down by
    hand — the evidence was a few rows below one that would not parse.

    Nought rather than a raise or a sentinel, because ``vmid`` already means
    "which guest" and every reader compares it to a guest's own id. A task
    about the node matches no guest, which is exactly true.
    """
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _with_polls(record: TaskRecord, polls: int) -> TaskRecord:
    """Return ``record`` carrying how many times it was asked for."""
    from dataclasses import replace

    return replace(record, polls=polls)


async def _pause(seconds: float) -> None:
    """Wait between task polls.

    A function rather than an inline call so that the poll cadence has one name,
    and so that the retry the base client owns stays visibly separate from the
    waiting a long-running task needs.
    """
    import asyncio as _asyncio

    await _asyncio.sleep(seconds)


def _switch(raw: Any) -> bool:
    """Return whether a corosync setting is on, in any of the spellings it takes.

    Absence is the finding rather than a default worth hiding: a two-node cluster
    with neither ``two_node`` nor ``wait_for_all`` has a quorum margin of zero,
    and this is the function that decides it did not find them.
    """
    return str(raw if raw is not None else "0").strip().lower() in {"1", "true", "on", "yes"}


def _declared_links(nodes: Sequence[Mapping[str, Any]]) -> dict[int, tuple[str, ...]]:
    """Return which nodes declare each corosync ring, from ``ringN_addr`` keys.

    Corosync numbers its rings and each node declares its own address on each.
    Collecting them by ring is what makes a ring only one node has visible as
    what it is: a link that can never come up, because links are pairwise.
    """
    found: dict[int, list[str]] = {}
    for row in nodes:
        name = str(row.get("node", ""))
        for key in row:
            text = str(key)
            if not (text.startswith("ring") and text.endswith("_addr")):
                continue
            index = text.removeprefix("ring").removesuffix("_addr")
            if index.isdigit():
                found.setdefault(int(index), []).append(name)
    return {ring: tuple(names) for ring, names in sorted(found.items())}


def _vmids(raw: Any) -> tuple[int, ...]:
    """Return the guest ids a backup job names, from Proxmox's comma-separated list."""
    if isinstance(raw, int):
        return (raw,)
    text = str(raw or "").strip()
    if not text:
        return ()
    return tuple(int(part) for part in text.split(",") if part.strip().isdigit())


def _vmid_of(volume: str) -> int:
    """Return the guest a thin volume belongs to, from its ``vm-<id>-disk-N`` name."""
    parts = volume.split("-")
    return int(parts[1]) if len(parts) > 2 and parts[0] == "vm" and parts[1].isdigit() else 0


def _pve_version(raw: str) -> str:
    """Return the bare version from Proxmox's ``pve-manager/9.2.6`` string."""
    return raw.split("/")[-1] if "/" in raw else raw


__all__ = [
    "GUEST_KINDS",
    "MAX_TASKS",
    "MAX_TASK_LOG_LINES",
    "MAX_TASK_POLLS",
    "NODE_UNREACHABLE_STATUS",
    "PAGINATION",
    "TASK_POLL_SECONDS",
    "ProxmoxClient",
]
