"""Everything a Proxmox cluster contains, as the estate's own resources.

Proxmox is the first integration to implement feature 038's discovery protocol,
and it is a good first one: a hypervisor already knows the whole shape. The
cluster knows its nodes, the nodes know their guests, the guests know which
datastore they sit on. None of the parentage has to be inferred from naming
conventions, which is what makes this estate trustworthy in a way a
tag-reconstructed one is not.

**One cluster-wide call carries most of it.** ``/cluster/resources`` returns every
node, guest and datastore in a single answer. Fifty guests times several
per-guest reads is a call budget nobody has, so the sweep takes the wide answer
and reserves per-guest reads for the one thing it cannot get from it: when each
guest was created, which is what keeps a reused VMID from inheriting a dead
guest's history.

**A node that is down is read, not skipped.** Its guests are still in the
cluster-wide list, so they are emitted with the status Proxmox gave them —
``unknown`` — and a signal saying the node hosting them is not answering. A sweep
that dropped them would let a completed full sweep conclude they had been
deleted, and the estate would decommission every guest on a node that was
rebooting.

**The sweep suspends; it never truncates.** Running out of calls, seconds or
resources produces an incomplete page with a cursor, and the next sweep resumes
there. That is what makes "this integration's whole inventory" a claim rather
than "as much of it as fitted".

**Nothing here writes, and nothing here can.** Every call is a read on the
client, which has no write methods, and a guest's configuration passes through
the deployment's masking rules before any of it becomes an attribute.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from integrations._base.discovery import DiscoveredResource, DiscoveryPage, declare
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.identity import (
    backup_job_identity,
    cluster_identity,
    creation_time,
    datastore_identity,
    disk_identity,
    guest_identity,
    node_identity,
    pool_identity,
    replication_job_identity,
)
from integrations.proxmox.models import BackupJob, ClusterStatus
from integrations.proxmox.redaction import masked_configuration, redacted_keys
from integrations.proxmox.schema import INTEGRATION
from platform.estate.attributes import AttributeType
from platform.estate.discovery.port import DiscoveryMode, SweepBudget
from platform.estate.kinds import (
    KIND_BACKUP_JOB,
    KIND_CLUSTER,
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    ResourceKind,
)

#: The three kinds Proxmox adds to the core set. Registered by the integration
#: rather than declared in ``platform``: a hypervisor's thin pool is not a
#: universal concept, and a core model that grew a field per vendor would stop
#: being a model.
KIND_STORAGE_POOL: Final = "storage_pool"
KIND_REPLICATION_JOB: Final = "replication_job"
KIND_PHYSICAL_DISK: Final = "physical_disk"

PROXMOX_KINDS: Final[tuple[ResourceKind, ...]] = (
    ResourceKind(
        name=KIND_STORAGE_POOL,
        label="Storage pool",
        integration=INTEGRATION,
        description=(
            "An LVM-thin pool. Two independent ways to fill up: its data extent, and its "
            "metadata — which stops the pool accepting writes while the data figure still "
            "looks comfortable."
        ),
        parent_kinds=(KIND_NODE,),
        attributes={
            "total_bytes": AttributeType.INTEGER,
            "data_percent": AttributeType.FLOAT,
            "metadata_percent": AttributeType.FLOAT,
            "volume_group": AttributeType.STRING,
        },
    ),
    ResourceKind(
        name=KIND_REPLICATION_JOB,
        label="Replication job",
        integration=INTEGRATION,
        # A job that runs every fifteen minutes observed hourly is stale; the
        # interval is an hour plus a sweep, so one missed run is not staleness.
        freshness_seconds=4_500,
        description="Recurring storage replication of one guest between two nodes.",
        parent_kinds=(KIND_NODE,),
        attributes={
            "enabled": AttributeType.BOOLEAN,
            "last_sync_at": AttributeType.TIMESTAMP,
            "fail_count": AttributeType.INTEGER,
        },
    ),
    ResourceKind(
        name=KIND_PHYSICAL_DISK,
        label="Physical disk",
        integration=INTEGRATION,
        description="A disk in a node, with the verdict its own firmware gives.",
        parent_kinds=(KIND_NODE,),
        attributes={
            "size_bytes": AttributeType.INTEGER,
            "model": AttributeType.STRING,
            "serial": AttributeType.STRING,
            "wearout": AttributeType.STRING,
        },
    ),
)

#: Every kind this source emits.
DISCOVERED_KINDS: Final[tuple[str, ...]] = (
    KIND_CLUSTER,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_STORAGE_POOL,
    KIND_BACKUP_JOB,
    KIND_REPLICATION_JOB,
    KIND_PHYSICAL_DISK,
)

#: How often a Proxmox cluster is swept. Five minutes: a hypervisor's inventory
#: changes when an operator changes it, and a guest created by hand should appear
#: while they are still looking at the screen.
DISCOVERY_INTERVAL_SECONDS: Final = 300

#: What a Proxmox node will tolerate. Its API is a Perl daemon on somebody's own
#: hardware rather than a cloud endpoint, and the reference cluster's primary
#: node sits at 63% CPU before anything asks it a question.
RATE_LIMIT_PER_MINUTE: Final = 120

#: NFR-001, declared. A two-node cluster with fifty guests costs two cluster-wide
#: calls, six cluster-detail calls, four per node, and one per guest — 66 for the
#: reference shape, and this is the ceiling with room for a cluster twice its size.
MAX_SWEEP_CALLS: Final = 150

#: Cursor stages, in the order the sweep runs them. Strings rather than an enum
#: because a cursor is stored and returned by the scheduler, and a stored enum
#: value is a string with extra steps between it and the thing that reads it.
STAGE_CLUSTER: Final = "cluster"
STAGE_DETAIL: Final = "detail"
STAGE_NODES: Final = "nodes"
STAGE_GUESTS: Final = "guests"


@dataclass(slots=True)
class _Spend:
    """What one sweep has spent so far, against what it was allowed."""

    budget: SweepBudget
    started: float
    calls: int = 0
    resources: int = 0

    def spend(self, calls: int = 1) -> None:
        """Record ``calls`` provider calls."""
        self.calls += calls

    @property
    def exhausted(self) -> bool:
        """Return whether this sweep must stop and come back at its cursor."""
        return (
            self.calls >= self.budget.max_provider_calls
            or self.resources >= self.budget.max_resources
            or (time.monotonic() - self.started) >= self.budget.max_seconds
        )


@dataclass(slots=True)
class ProxmoxDiscovery:
    """A Proxmox cluster, as resources, reached without holding a credential.

    ``client`` may be ``None`` for the declaration alone — composition asks a
    source what it emits before it has anywhere to point it, and a declaration
    that needed a connection would make the registry's validation a network
    operation.
    """

    client: ProxmoxClient | None = None
    #: Whatever the observability bridge publishes per node, keyed by node name.
    #: The three readings the Proxmox API does not have arrive this way or not at
    #: all; see ``supplementary.py`` for why not over SSH.
    published: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @property
    def declaration(self) -> Any:
        """Return what this source says about itself: kinds, interval, bounds."""
        return declare(
            INTEGRATION,
            kinds=DISCOVERED_KINDS,
            interval_seconds=DISCOVERY_INTERVAL_SECONDS,
            rate_limit_per_minute=RATE_LIMIT_PER_MINUTE,
            max_provider_calls=MAX_SWEEP_CALLS,
        )

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the next page of what this cluster contains.

        The stages run in order and the cursor names the one to resume at.
        Resuming re-reads the two cluster-wide calls, because the node list and
        the guest list are what every later stage indexes into — and paying two
        calls to rebuild them is cheaper than storing a snapshot whose staleness
        nobody could reason about.

        Only a ``FULL`` sweep that reached the end reports ``complete``. This
        source declares no incremental support, so it should never be asked for
        one — but a page that claimed completeness for a delta would license the
        estate to mark absent everything the delta did not mention, and that is
        too expensive a mistake to leave to a caller's good manners.
        """
        client = self._require_client()
        spend = _Spend(budget=budget, started=time.monotonic())
        resources: list[DiscoveredResource] = []

        status = await self._cluster_status(client, spend)
        raw = tuple(await client.cluster_resources())
        spend.spend()
        cluster = status.name or "standalone"
        nodes = tuple(member.name for member in status.members)
        offline = set(status.offline_nodes)

        stage, position = _parse_cursor(cursor)

        if stage == STAGE_CLUSTER:
            resources.append(_cluster_resource(cluster, status))
            resources.extend(_node_resources(cluster, status, raw))
            resources.extend(_datastore_resources(cluster, raw))
            spend.resources = len(resources)
            if spend.exhausted:
                return _page(resources, spend, cursor=_cursor(STAGE_DETAIL, 0))
            stage, position = STAGE_DETAIL, 0

        if stage == STAGE_DETAIL:
            emitted, stopped = await self._detail_stage(client, spend, cluster)
            resources.extend(emitted)
            spend.resources = len(resources)
            if stopped or spend.exhausted:
                return _page(resources, spend, cursor=_cursor(STAGE_NODES, 0))
            stage, position = STAGE_NODES, 0

        if stage == STAGE_NODES:
            for index in range(position, len(nodes)):
                if spend.exhausted:
                    return _page(resources, spend, cursor=_cursor(STAGE_NODES, index))
                resources.extend(await self._node_detail(client, spend, cluster, nodes[index]))
                spend.resources = len(resources)
            stage, position = STAGE_GUESTS, 0

        guests = tuple(row for row in raw if row.get("type") in {"lxc", "qemu"})
        for index in range(position if stage == STAGE_GUESTS else 0, len(guests)):
            if spend.exhausted:
                return _page(resources, spend, cursor=_cursor(STAGE_GUESTS, index))
            resources.append(await self._guest(client, spend, cluster, guests[index], offline))
            spend.resources = len(resources)

        return _page(resources, spend, cursor="", complete=mode is DiscoveryMode.FULL)

    # -- stages ---------------------------------------------------------------

    async def _cluster_status(self, client: ProxmoxClient, spend: _Spend) -> ClusterStatus:
        """Return the cluster's membership and quorum, counting the call."""
        status = await client.cluster_status()
        spend.spend()
        return status

    async def _detail_stage(
        self,
        client: ProxmoxClient,
        spend: _Spend,
        cluster: str,
    ) -> tuple[list[DiscoveredResource], bool]:
        """Return the cluster-wide detail, and whether the budget stopped it short."""
        emitted: list[DiscoveredResource] = []

        await client.cluster_configuration()
        spend.spend(2)
        if spend.exhausted:
            return emitted, True

        await client.high_availability()
        spend.spend(3)
        if spend.exhausted:
            return emitted, True

        jobs = await client.backup_jobs()
        spend.spend()
        emitted.extend(_backup_job_resource(cluster, job) for job in jobs)
        return emitted, False

    async def _node_detail(
        self,
        client: ProxmoxClient,
        spend: _Spend,
        cluster: str,
        node: str,
    ) -> list[DiscoveredResource]:
        """Return the disks, thin pools and replication jobs on one node."""
        parent = node_identity(cluster, node)
        emitted: list[DiscoveredResource] = []

        disks = await client.node_disks(node)
        spend.spend()
        emitted.extend(
            DiscoveredResource(
                kind=KIND_PHYSICAL_DISK,
                native_id=disk_identity(cluster, node, disk.serial, disk.device),
                display_name=disk.device,
                correlation_key=disk.serial,
                parent_native_id=parent,
                provider_status=disk.smart_health or "unknown",
                attributes={
                    "size_bytes": disk.size_bytes,
                    "model": disk.model,
                    "serial": disk.serial,
                    "wearout": disk.wearout,
                },
                signals={"disk_type": disk.disk_type, "smart": disk.smart_health or "unknown"},
            )
            for disk in disks
        )

        pools = await client.thin_pools(node)
        spend.spend()
        volumes = await client.thin_volumes(node)
        spend.spend()
        by_group: dict[str, list[Any]] = {}
        for volume in volumes:
            by_group.setdefault(volume.volume_group, []).append(volume)
        emitted.extend(
            DiscoveredResource(
                kind=KIND_STORAGE_POOL,
                native_id=pool_identity(cluster, node, pool.volume_group, pool.name),
                display_name=pool.name,
                parent_native_id=parent,
                provider_status=pool.state or "available",
                attributes={
                    "total_bytes": pool.size_bytes,
                    "data_percent": pool.data_percent,
                    "metadata_percent": pool.metadata_percent,
                    "volume_group": pool.volume_group,
                },
                signals={
                    "data_percent": str(pool.data_percent),
                    "metadata_percent": str(pool.metadata_percent),
                    "metadata_critical": "yes" if pool.metadata_critical else "no",
                    "volumes_near_full": ",".join(
                        volume.name
                        for volume in by_group.get(pool.volume_group, ())
                        if volume.near_full
                    ),
                },
            )
            for pool in pools
        )

        jobs = await client.replication_jobs(node)
        spend.spend()
        emitted.extend(
            DiscoveredResource(
                kind=KIND_REPLICATION_JOB,
                native_id=replication_job_identity(cluster, job.job_id),
                display_name=f"{job.guest}: {job.source} → {job.target}",
                parent_native_id=parent,
                provider_status="failed" if job.failing else "ok",
                attributes={
                    "enabled": job.enabled,
                    "fail_count": job.fail_count,
                },
                signals={
                    "source": job.source,
                    "target": job.target,
                    "guest": str(job.guest),
                    "last_sync": str(job.last_sync),
                },
            )
            for job in jobs
        )
        return emitted

    async def _guest(
        self,
        client: ProxmoxClient,
        spend: _Spend,
        cluster: str,
        row: Mapping[str, Any],
        offline: set[str],
    ) -> DiscoveredResource:
        """Return one guest, identified by when it was created and masked before storage."""
        kind = str(row.get("type", ""))
        vmid = int(row.get("vmid", 0) or 0)
        node = str(row.get("node", ""))

        configuration: Mapping[str, Any] = {}
        try:
            configuration = await client.guest_configuration(node, vmid, kind=kind)
        except IntegrationError:
            # A guest on a node that is not answering. The cluster-wide list
            # still knows it exists, which is exactly why it must be emitted:
            # dropping it would let a complete sweep conclude it was deleted.
            configuration = {}
        spend.spend()

        created = creation_time(configuration)
        masked = masked_configuration(configuration)
        signals = {
            "node": node,
            "identity_discriminator": created or "unavailable",
            "redacted_fields": ",".join(redacted_keys(configuration)),
        }
        if node in offline:
            signals["stale"] = "the node hosting it is not answering"

        attributes: dict[str, Any] = {
            "cores": int(row.get("maxcpu", 0) or 0),
            "memory_bytes": int(row.get("maxmem", 0) or 0),
        }
        if kind == "qemu":
            attributes["disk_bytes"] = int(row.get("maxdisk", 0) or 0)
            attributes["operating_system"] = str(masked.get("ostype", ""))
            attributes["boot_order"] = str(masked.get("boot", ""))
        else:
            attributes["image"] = str(masked.get("ostype", ""))

        return DiscoveredResource(
            kind=KIND_CONTAINER if kind == "lxc" else KIND_VIRTUAL_MACHINE,
            native_id=guest_identity(cluster, kind, vmid, created_at=created),
            display_name=str(row.get("name", "")) or f"{kind}/{vmid}",
            correlation_key=f"{cluster}/{kind}/{vmid}",
            parent_native_id=node_identity(cluster, node),
            provider_status=_guest_status(row),
            attributes=attributes,
            labels=(kind,),
            signals=signals,
        )

    def _require_client(self) -> ProxmoxClient:
        """Return the client, or say that this source was never pointed anywhere."""
        if self.client is None:
            raise ValueError(
                "this Proxmox discovery source has no client, so it can declare what it "
                "would emit and cannot sweep. Composition wires one in."
            )
        return self.client


# --- Building resources -------------------------------------------------------


def _cluster_resource(cluster: str, status: ClusterStatus) -> DiscoveredResource:
    """Return the cluster itself, with quorum recorded as a fact."""
    return DiscoveredResource(
        kind=KIND_CLUSTER,
        native_id=cluster_identity(cluster),
        display_name=cluster,
        provider_status="quorate" if status.quorate else "degraded",
        attributes={
            "node_count": len(status.members),
            "quorate": status.quorate,
            "version": status.version,
        },
        signals={
            "quorum_margin": str(status.quorum_margin),
            "expected_votes": str(status.expected_votes),
            "total_votes": str(status.total_votes),
            "clustered": "yes" if status.is_clustered else "no",
            "quorum_device": status.quorum_device,
            "quorum_device_contributes": (
                "no" if status.has_non_contributing_quorum_device else "yes"
            ),
            "offline_nodes": ",".join(status.offline_nodes),
        },
    )


def _node_resources(
    cluster: str,
    status: ClusterStatus,
    raw: Sequence[Mapping[str, Any]],
) -> list[DiscoveredResource]:
    """Return one resource per node, from the cluster-wide list and the membership view."""
    wide = {str(row.get("node", "")): row for row in raw if row.get("type") == "node"}
    emitted: list[DiscoveredResource] = []
    for member in status.members:
        row = wide.get(member.name, {})
        emitted.append(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id=node_identity(cluster, member.name),
                display_name=member.name,
                correlation_key=member.name,
                parent_native_id=cluster_identity(cluster),
                provider_status=str(row.get("status", "online" if member.online else "offline")),
                attributes={
                    "cpu_count": int(row.get("maxcpu", 0) or 0),
                    "memory_bytes": int(row.get("maxmem", 0) or 0),
                    "uptime_seconds": int(row.get("uptime", 0) or 0),
                },
                signals={
                    "address": member.address,
                    "node_id": str(member.node_id),
                    "online": "yes" if member.online else "no",
                },
            )
        )
    return emitted


def _datastore_resources(
    cluster: str, raw: Sequence[Mapping[str, Any]]
) -> list[DiscoveredResource]:
    """Return one resource per datastore per node that can see it.

    Per node rather than per name. A share visible from one node and not another
    is the reference cluster's state, and a single record would have to choose
    which node's view of it to believe.
    """
    emitted: list[DiscoveredResource] = []
    for row in raw:
        if row.get("type") != "storage":
            continue
        node = str(row.get("node", ""))
        name = str(row.get("storage", ""))
        emitted.append(
            DiscoveredResource(
                kind=KIND_DATASTORE,
                native_id=datastore_identity(cluster, node, name),
                display_name=name,
                parent_native_id=node_identity(cluster, node),
                provider_status=str(row.get("status", "unknown")),
                attributes={
                    "total_bytes": int(row.get("maxdisk", 0) or 0),
                    "used_bytes": int(row.get("disk", 0) or 0),
                    "storage_type": str(row.get("plugintype", "")),
                    "shared": bool(int(row.get("shared", 0) or 0)),
                },
                signals={"node": node},
            )
        )
    return emitted


def _backup_job_resource(cluster: str, job: BackupJob) -> DiscoveredResource:
    """Return one backup job, with what it covers and whether it is switched on."""
    return DiscoveredResource(
        kind=KIND_BACKUP_JOB,
        native_id=backup_job_identity(cluster, job.job_id),
        display_name=job.comment or job.job_id,
        parent_native_id=cluster_identity(cluster),
        provider_status="enabled" if job.enabled else "disabled",
        attributes={
            "schedule": job.schedule,
            "enabled": job.enabled,
            "covered_count": len(job.vmids),
        },
        signals={
            "covers": job.covers,
            "covered_vmids": ",".join(str(vmid) for vmid in job.vmids),
            "storage": job.storage,
            "retention": job.retention,
        },
    )


def _guest_status(row: Mapping[str, Any]) -> str:
    """Return the status word for a guest, preferring what Proxmox itself said."""
    if int(row.get("template", 0) or 0):
        return "template"
    return str(row.get("status", "unknown"))


def _page(
    resources: Sequence[DiscoveredResource],
    spend: _Spend,
    *,
    cursor: str,
    complete: bool = False,
) -> DiscoveryPage:
    """Return the page one call to ``discover`` produced."""
    return DiscoveryPage(
        resources=tuple(resources),
        complete=complete,
        cursor=cursor,
        provider_calls=spend.calls,
    )


def _cursor(stage: str, position: int) -> str:
    """Return the cursor that resumes at ``stage``, item ``position``."""
    return f"{stage}:{position}"


def _parse_cursor(cursor: str) -> tuple[str, int]:
    """Return the stage and position a cursor names, or the start of the sweep."""
    if not cursor:
        return STAGE_CLUSTER, 0
    stage, _, position = cursor.partition(":")
    return (stage or STAGE_CLUSTER), (int(position) if position.isdigit() else 0)


__all__ = [
    "DISCOVERED_KINDS",
    "DISCOVERY_INTERVAL_SECONDS",
    "KIND_PHYSICAL_DISK",
    "KIND_REPLICATION_JOB",
    "KIND_STORAGE_POOL",
    "MAX_SWEEP_CALLS",
    "PROXMOX_KINDS",
    "RATE_LIMIT_PER_MINUTE",
    "ProxmoxDiscovery",
]
