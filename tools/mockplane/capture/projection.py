"""Turning a direct read of the cluster into the shapes the future endpoints return.

Nothing serves the estate inventory, continuous observation, or anything
Proxmox-shaped yet, and the screens this dataset exists for are built around all
three. So the reads are projected: assembled here into the response bodies
``fixtures/contract/projected.json`` declares, so the fixtures are wrong in the
same way the real endpoints would be wrong rather than in a way of their own.

The observation half is derived rather than invented. Each detector is a
predicate over what was actually read — a quorum with no margin, a guest at 99%
of its own volume while its datastore reads 84%, a backup job that exists and is
switched off — and an observation exists because a read made it true. Inventing
incidents would have produced a tidy dataset and would have told the console
nothing about what it will meet.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from platform.estate.alert_resolution import UNRESOLVED_TARGET_PREFIX
from platform.estate.signal_map import signal_map_for
from platform.persistence.ports.estate_repository import Resource
from tools.mockplane.capture.parsers import (
    BootReading,
    MountReading,
    PackageReading,
    QuorumReading,
    ThinPoolReading,
    VolumeReading,
)
from tools.mockplane.records import CapturedRecord, Provenance, Request

#: A datastore this full is a finding rather than a warning: there is no
#: sequence of events from here that ends well without somebody acting.
DATASTORE_CRITICAL_PERCENT: Final = 95.0
DATASTORE_HIGH_PERCENT: Final = 90.0

#: A guest at this much of its own volume, which is a different question from
#: its datastore's fill and the one a datastore-level threshold cannot ask.
VOLUME_HIGH_PERCENT: Final = 93.0

#: Thin-pool metadata exhaustion takes a pool offline while its data percentage
#: still reads comfortable. Absent from every API level.
POOL_METADATA_HIGH_PERCENT: Final = 30.0

#: Retention this shallow means the second failed backup destroys the recovery
#: point the first one left.
SHALLOW_RETENTION_KEEP_LAST: Final = 2


@dataclass(frozen=True, slots=True)
class GuestReading:
    """One guest as the cluster's own API reports it."""

    vmid: str
    name: str
    kind: str
    node: str
    state: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DatastoreReading:
    """One datastore, including the two that answer ``unknown``."""

    name: str
    node: str
    kind: str
    used_bytes: int | None
    total_bytes: int | None
    status: str


@dataclass(frozen=True, slots=True)
class BackupJobReading:
    """One backup job, including the ones that exist and are switched off."""

    job_id: str
    comment: str
    node: str | None
    schedule: str
    enabled: bool
    covers_all: bool
    vmids: tuple[str, ...]
    keep_last: int
    last_run_at: str | None = None


@dataclass(frozen=True, slots=True)
class NodeReading:
    """Everything read from one node, from both the API and the shell."""

    name: str
    role: str
    version: str
    kernel_running: str
    kernel_installed: str
    cpu_percent: float
    memory_percent: float
    root_filesystem_percent: float
    failed_units: tuple[str, ...] = field(default_factory=tuple)
    thin_pools: tuple[ThinPoolReading, ...] = field(default_factory=tuple)
    volumes: tuple[VolumeReading, ...] = field(default_factory=tuple)
    mounts: tuple[MountReading, ...] = field(default_factory=tuple)
    boots: tuple[BootReading, ...] = field(default_factory=tuple)
    packages: tuple[PackageReading, ...] = field(default_factory=tuple)
    bridges: tuple[str, ...] = field(default_factory=tuple)
    zfs_pools: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ClusterReading:
    """One capture of one cluster, both sources merged."""

    captured_at: str
    nodes: tuple[NodeReading, ...]
    guests: tuple[GuestReading, ...]
    datastores: tuple[DatastoreReading, ...]
    backup_jobs: tuple[BackupJobReading, ...]
    quorum: QuorumReading
    replication_jobs: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Detector:
    """One shipped check, the signal it reads, and the severity a finding carries.

    ``signal`` is what the detector endpoint reports beside the name, because a
    threshold an operator is deciding whether to change is only reviewable
    against the measurement it is a threshold on.
    """

    detector_id: str
    name: str
    description: str
    severity: str
    signal: str


#: The detectors, each corresponding to a condition observed in a real cluster
#: or named in a real postmortem. Declared here because the projection is what
#: evaluates them; the shipped implementations arrive with the guardian work.
DETECTORS: Final[tuple[Detector, ...]] = (
    Detector(
        "quorum-margin-zero",
        "Quorum margin is zero",
        "Losing either node drops the cluster below its quorum, at which point the "
        "cluster filesystem goes read-only and no guest can be started, stopped or migrated.",
        "critical",
        "cluster.quorum_margin",
    ),
    Detector(
        "quorum-device-not-contributing",
        "Quorum device configured but contributing nothing",
        "A quorum device appears in the membership view and carries no votes, which reads "
        "as configured to anything that counts devices rather than votes.",
        "critical",
        "cluster.quorum_device_votes",
    ),
    Detector(
        "backup-job-disabled",
        "Backup job exists and is disabled",
        "A disabled job is indistinguishable from a job that ran, in every view that lists jobs.",
        "critical",
        "backup.job_enabled",
    ),
    Detector(
        "guest-uncovered-by-backup",
        "Guest covered by no enabled backup job",
        "Coverage is the question, not job count: a guest named only by a disabled job has none.",
        "critical",
        "backup.guest_covered",
    ),
    Detector(
        "datastore-near-full",
        "Datastore near full",
        "A datastore above its threshold, measured against the datastore rather than "
        "against any one guest on it.",
        "critical",
        "storage.used_percent",
    ),
    Detector(
        "guest-volume-near-full",
        "Guest volume near full",
        "A guest at the ceiling of its own volume while its datastore still reads "
        "comfortable — the distinction a datastore-level threshold cannot make.",
        "high",
        "storage.volume_used_percent",
    ),
    Detector(
        "thin-pool-metadata-pressure",
        "Thin-pool metadata under pressure",
        "Metadata exhaustion takes a pool offline while its data percentage still looks fine.",
        "medium",
        "storage.thin_metadata_percent",
    ),
    Detector(
        "kernel-never-booted",
        "Kernel installed and never booted",
        "The first real boot of an installed-but-unbooted kernel will be an unplanned one.",
        "high",
        "node.kernel_pending",
    ),
    Detector(
        "no-replication-node-local-storage",
        "No replication with node-local guest storage",
        "Losing a node makes its guests unavailable until they are restored from a backup.",
        "high",
        "guest.replication_configured",
    ),
    Detector(
        "failed-systemd-units",
        "Failed units on a node",
        "Absent from every API level, and where a silent degradation becomes visible.",
        "medium",
        "node.failed_units",
    ),
    Detector(
        "datastore-status-unknown",
        "Datastore reporting unknown",
        "A share that is down still appears in the inventory; only its status says so.",
        "medium",
        "storage.status",
    ),
    Detector(
        "security-updates-pending",
        "Security updates pending",
        "Counted separately from the rest, because the rest can wait for a window.",
        "medium",
        "node.security_updates",
    ),
    Detector(
        "bridge-absent",
        "A configured bridge does not exist",
        "Everything depends on the bridge and nothing watches it; a rename underneath it "
        "took a whole cluster off the network.",
        "high",
        "node.bridge_present",
    ),
    Detector(
        "shallow-backup-retention",
        "Backup retention shallow",
        "With two recovery points, the second failed backup destroys what the first left.",
        "medium",
        "backup.retention_depth",
    ),
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What one detector saw about one subject, at one instant."""

    observation_id: str
    detector: str
    subject: str
    verdict: str
    severity: str
    observed_at: str
    detail: str
    evidence: Mapping[str, Any]


def resource_id_of(guest: GuestReading) -> str:
    """Return the estate identifier of one guest."""
    return f"{'ct' if guest.kind == 'container' else 'vm'}-{guest.vmid}"


def node_resource_id(name: str) -> str:
    """Return the estate identifier of one node."""
    return f"node-{name}"


#: The zones the fixture cluster is divided into, and the criticalities its
#: owner grades guests with. Deliberately uneven: a screen that groups and
#: filters is only exercised by a distribution somebody would actually see, and
#: a few guests are left ungraded because a real inventory always has some.
_DECLARED_ZONES = ("apps", "dmz", "infra", "ci")
_DECLARED_CRITICALITY = ("high", "medium", "medium", "low")


def _declared(guest: GuestReading) -> dict[str, str]:
    """Return the annotations a read inventory would have put on ``guest``.

    Derived from the vmid so the fixture is the same every time it is built —
    a dataset that shuffled would make every baseline a diff.
    """
    try:
        number = int(guest.vmid)
    except ValueError:
        return {}
    declared = {"zone": _DECLARED_ZONES[number % len(_DECLARED_ZONES)]}
    if number % 7:
        # Every seventh guest is ungraded, because a real inventory always has
        # some nobody has got round to.
        declared["criticality"] = _DECLARED_CRITICALITY[number % len(_DECLARED_CRITICALITY)]
    return declared


def estate(reading: ClusterReading) -> tuple[CapturedRecord, ...]:
    """Return the endpoints the *gateway* serves, from one cluster reading.

    Not a projection. These endpoints exist, so their records are marked
    ``gateway`` and are built in the shape the route returns — field for field.
    What used to be a projection of a cluster read into a shape nothing answered
    is now a *rendering* of the same read into the shape the API sends, so a
    console reading a fixture and a console reading a deployment are reading one
    thing.

    Kept in this module rather than beside the recorded gateway payloads because
    the cluster reading is what it is built from, and everything that knows how
    to turn a reading into a resource is here.
    """
    observations = tuple(_observations(reading))
    incidents = (*_incidents(reading, observations), *_alert_incidents(reading))
    records: list[CapturedRecord] = [
        _record("estate-summary", {}, _summary(reading), Provenance.GATEWAY),
        _record("estate-resources", {}, {"resources": _resources(reading)}, Provenance.GATEWAY),
        _record(
            "estate-unresolved-targets",
            {},
            {"targets": _unresolved_targets(incidents)},
            Provenance.GATEWAY,
        ),
        _record("incidents", {}, {"incidents": list(incidents)}, Provenance.GATEWAY),
        _record(
            "detectors", {}, {"detectors": _detectors(reading, observations)}, Provenance.GATEWAY
        ),
        _record(
            "observations",
            {},
            {"observations": [_as_json(item) for item in observations]},
            Provenance.GATEWAY,
        ),
    ]
    for incident in incidents:
        records.append(
            _record(
                "incident-detail",
                {"incident_id": incident["incident_id"]},
                {
                    "incident": incident,
                    "observations": [
                        _as_json(item)
                        for item in observations
                        if item.detector == incident["detector"]
                        and item.subject in incident["subjects"]
                    ],
                    "timeline": _timeline(incident),
                },
                Provenance.GATEWAY,
            )
        )
    resources = _resources(reading)
    volumes = _volumes(reading)
    for resource in resources:
        records.append(
            _record(
                "estate-resource-detail",
                {"resource_id": resource["resource_id"]},
                {
                    "resource": resource,
                    "derivation": {
                        "state": resource["health"],
                        "rule": "provider_status",
                        "derived_at": reading.captured_at,
                        "signals": [
                            {
                                "name": check["check"],
                                "value": check["verdict"],
                                "observed_at": reading.captured_at,
                                "source": _SOURCE,
                            }
                            for check in _health(resource, observations)
                        ],
                        "raw_status": resource["health"],
                        "explanation": resource["explanation"],
                    },
                    "signals": _signals(resource),
                    "rollup_rule": "majority_healthy" if resource["kind"] == "node" else "own_only",
                    "freshness_seconds": 3600,
                    "contributions": [
                        {
                            "integration": _SOURCE,
                            "native_id": resource["native_id"],
                            "display_name": resource["display_name"],
                            "observed_at": reading.captured_at,
                        }
                    ],
                    "transitions": [],
                    "references": [
                        {
                            "reference_kind": "incident",
                            "reference_id": incident["incident_id"],
                            "recorded_at": reading.captured_at,
                            "summary": "",
                        }
                        for incident in incidents
                        if resource["resource_id"] in incident["subjects"]
                    ],
                    "children": [
                        child
                        for child in resources
                        if child["parent_id"] == resource["resource_id"]
                    ],
                    "parent": next(
                        (
                            other
                            for other in resources
                            if other["resource_id"] == resource["parent_id"]
                        ),
                        None,
                    ),
                    "volumes": [
                        volume
                        for volume in volumes
                        if volume["resource_id"] == resource["resource_id"]
                    ],
                },
                Provenance.GATEWAY,
            )
        )

    return tuple(records)


def project(reading: ClusterReading) -> tuple[CapturedRecord, ...]:
    """Return one record per projected endpoint, from one cluster reading.

    Every record is marked ``pvesh`` or ``shell`` according to which source
    carried the fact it rests on. A projection built from both is attributed to
    the shell, because the shell half is the part that has no gateway
    equivalent and therefore the part that survives the handover.

    Only the three Proxmox-shaped endpoints are here now. The estate's own and
    continuous observation's are ``estate`` above, because the gateway serves
    them — and a projection for an endpoint that already exists would be the
    fallback this module's split exists to prevent.
    """
    return (
        _record("estate-nodes", {}, {"nodes": _nodes(reading)}, Provenance.SHELL),
        _record("estate-storage", {}, _storage(reading), Provenance.SHELL),
        _record("estate-backups", {}, {"jobs": _backups(reading)}, Provenance.PVESH),
    )


# --- The estate ------------------------------------------------------------------


def _absent_vmid(reading: ClusterReading) -> str:
    """Return a guest identifier this reading provably does not hold.

    One past the highest it carries, so the fixture cannot drift from the
    cluster it describes: a reading that later gains that guest produces a
    different finding rather than a fixture quietly asserting something untrue.
    """
    numbered = sorted(int(guest.vmid) for guest in reading.guests if guest.vmid.isdigit())
    return str(numbered[-1] + 1) if numbered else ""


def _alert_incidents(reading: ClusterReading) -> tuple[dict[str, Any], ...]:
    """Return the incidents an ingested alert raised, in the route's own shape.

    One, and it is the case this dataset had no example of: an alert whose
    target nothing in the estate holds. The subject is the finding rather than a
    resource, because there is no resource — which is the whole of what the
    ``unresolved-target:`` prefix means.
    """
    absent = _absent_vmid(reading)
    if not absent:
        return ()
    return (
        {
            "incident_id": "inc-alert-0001",
            "title": "ContainerMemoryHigh",
            "severity": "high",
            "state": "open",
            "origin": "alert",
            "opened_at": reading.captured_at,
            "closed_at": None,
            "subjects": [f"unresolved-target:{absent}"],
            "detector": "alertmanager",
            "run_id": None,
            "team_node_id": "",
            "self_resolved": False,
            "suppressed_by": "",
            "close_reason": "",
            "summary": (
                f"the alert is about hypervisor guest {absent}, and no guest in this estate "
                f"carries that identifier. Either it was created since the last sweep, or "
                f"this receiver is pointed at a deployment that does not watch that cluster"
            ),
        },
    )


def _unresolved_targets(incidents: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the unresolved alert targets ``incidents`` recorded.

    Read back off the incidents rather than built beside them, so the listing
    and the incident that is the record of it cannot disagree — which is the
    same derivation the route itself performs.
    """
    found: list[dict[str, Any]] = []
    for incident in incidents:
        for subject in incident["subjects"]:
            if not str(subject).startswith(UNRESOLVED_TARGET_PREFIX):
                continue
            found.append(
                {
                    "value": str(subject)[len(UNRESOLVED_TARGET_PREFIX) :],
                    "label": "vmid",
                    "zone": "",
                    "why": str(incident["summary"]),
                    "incident_id": str(incident["incident_id"]),
                    "alert_name": str(incident["title"]),
                    "observed_at": str(incident["opened_at"]),
                }
            )
    return found


def _record(
    slug: str, arguments: Mapping[str, str], body: Any, provenance: Provenance
) -> CapturedRecord:
    return CapturedRecord(
        slug=slug,
        arguments=dict(arguments),
        status=200,
        body=body,
        provenance=provenance,
        request=Request(command=f"projected from a direct read ({provenance.value})"),
    )


def _signals(resource: Mapping[str, Any]) -> dict[str, Any]:
    """Return which source answers each question about ``resource``.

    Derived by the deployment's own rule rather than written out here, so the
    dataset a screen is photographed against and the document a deployment
    serves are one thing. What is configured in this dataset is the hypervisor
    and nothing else — so "is it up" resolves and the rest come back as named
    gaps, which is exactly what an estate nobody has connected a log store to
    looks like, and is the state the empty-half of the panel exists for.
    """
    found = signal_map_for(
        Resource(
            resource_id=str(resource["resource_id"]),
            kind=str(resource["kind"]),
            source=str(resource["source"]),
            native_id=str(resource["native_id"]),
            display_name=str(resource["display_name"]),
            attributes=dict(resource["attributes"]),
            labels=tuple(str(label) for label in resource["labels"]),
        ),
        configured=(_SOURCE,),
    )
    record = found.to_record()
    return {"sources": record["sources"], "missing": record["missing"]}


def _resources(reading: ClusterReading) -> list[dict[str, Any]]:
    """Return the cluster's guests and nodes in the estate endpoint's own shape.

    The shape is the gateway's, field for field, because the gateway serves this
    endpoint now. What used to be a *projection* of a cluster read into a shape
    nothing answered is now a *rendering* of the same read into the shape the API
    returns — so a console reading a fixture and a console reading a deployment
    are reading one thing.

    The per-guest readings live under ``attributes``, which is where a Proxmox
    discovery puts them: the core kinds do not declare a fill percentage, and the
    integration that knows what one means declares a kind that does.
    """
    covered = _covered_resource_ids(reading)
    volumes_by_resource = {volume["resource_id"]: volume for volume in _volumes(reading)}
    node_names = {node_resource_id(node.name): node.name for node in reading.nodes}
    resources: list[dict[str, Any]] = []

    for guest in reading.guests:
        identifier = resource_id_of(guest)
        volume = volumes_by_resource.get(identifier)
        parent = node_resource_id(guest.node)
        state = _reported_health(guest.state)
        attributes: dict[str, Any] = {"backed_up": covered and identifier in covered}
        # What an estate whose declared inventory has been read looks like. Both
        # are annotations rather than anything the hypervisor reports: the zone
        # is derived from the guest's address against the declared networks, the
        # criticality is written down by whoever owns the estate. A fixture
        # without them exercises only the column that says nobody knows.
        attributes.update(_declared(guest))
        if guest.state == "running":
            attributes["cpu_percent"] = guest.cpu_percent
            attributes["memory_percent"] = guest.memory_percent
        if volume:
            attributes["volume_percent"] = volume["used_percent"]
            attributes["volume_id"] = volume["volume_id"]
        resources.append(
            {
                "resource_id": identifier,
                "kind": guest.kind,
                "display_name": guest.name,
                "health": state,
                "stored_health": state,
                "is_stale": False,
                "source": _SOURCE,
                "sources": [_SOURCE],
                "native_id": identifier,
                "parent_id": parent,
                "parent_name": node_names.get(parent, guest.node),
                "team_node_id": None,
                "labels": list(guest.tags),
                "attributes": attributes,
                "first_seen_at": reading.captured_at,
                "last_seen_at": reading.captured_at,
                "absent_since": None,
                "maintenance_until": None,
                "maintenance_reason": "",
                "explanation": _explanation(guest.state, state),
            }
        )

    for node in reading.nodes:
        state = _reported_health("online")
        resources.append(
            {
                "resource_id": node_resource_id(node.name),
                "kind": "node",
                "display_name": node.name,
                "health": state,
                "stored_health": state,
                "is_stale": False,
                "source": _SOURCE,
                "sources": [_SOURCE],
                "native_id": node_resource_id(node.name),
                "parent_id": None,
                "parent_name": "",
                "team_node_id": None,
                "labels": [node.role],
                "attributes": {
                    "cpu_percent": node.cpu_percent,
                    "memory_percent": node.memory_percent,
                    "volume_percent": node.root_filesystem_percent,
                },
                "first_seen_at": reading.captured_at,
                "last_seen_at": reading.captured_at,
                "absent_since": None,
                "maintenance_until": None,
                "maintenance_reason": "",
                "explanation": _explanation("online", state),
            }
        )
    return sorted(resources, key=lambda resource: str(resource["resource_id"]))


#: The integration this reading came from, as the estate names a source.
_SOURCE: Final = "proxmox"

#: How a hypervisor's lifecycle words land in the estate's closed set. The same
#: mapping the platform ships; repeated here rather than imported because
#: ``tools/`` is not packaged and a fixture generator that imported the platform
#: would make the fixture depend on the thing it is meant to stand in for.
_HEALTH_OF: Final[Mapping[str, str]] = {
    "running": "healthy",
    "online": "healthy",
    "stopped": "unhealthy",
    "paused": "maintenance",
}


def _reported_health(state: str) -> str:
    """Return the closed-set state ``state`` maps to, or ``unknown``."""
    return _HEALTH_OF.get(state, "unknown")


def _explanation(raw: str, state: str) -> str:
    """Return the sentence the endpoint puts on a resource in ``state``."""
    return f"the provider reported {raw!r}, which maps to {state}."


def _nodes(reading: ClusterReading) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node_resource_id(node.name),
            "name": node.name,
            "role": node.role,
            "version": node.version,
            "kernel_running": node.kernel_running,
            "kernel_installed": node.kernel_installed,
            "cpu_percent": node.cpu_percent,
            "memory_percent": node.memory_percent,
            "root_filesystem_percent": node.root_filesystem_percent,
            "guests": sum(1 for guest in reading.guests if guest.node == node.name),
            "quorum_votes": 1,
            "expected_votes": reading.quorum.expected_votes,
            "failed_units": list(node.failed_units),
            "bridges": list(node.bridges),
            "pending_updates": len(node.packages),
            "security_updates": sum(1 for package in node.packages if package.is_security),
        }
        for node in reading.nodes
    ]


def _volumes(reading: ClusterReading) -> list[dict[str, Any]]:
    by_vmid = {guest.vmid: resource_id_of(guest) for guest in reading.guests}
    volumes: list[dict[str, Any]] = []
    for node in reading.nodes:
        for volume in node.volumes:
            vmid = _vmid_of(volume.name)
            resource = by_vmid.get(vmid, "")
            if not resource:
                continue
            volumes.append(
                {
                    "volume_id": volume.name,
                    "resource_id": resource,
                    "node": node.name,
                    "pool": volume.pool,
                    "used_percent": volume.used_percent,
                    "size_bytes": volume.size_bytes,
                }
            )
    return sorted(volumes, key=lambda volume: str(volume["volume_id"]))


def _storage(reading: ClusterReading) -> dict[str, Any]:
    return {
        "datastores": [
            {
                "name": datastore.name,
                "node": datastore.node,
                "kind": datastore.kind,
                "used_bytes": datastore.used_bytes,
                "total_bytes": datastore.total_bytes,
                "used_percent": _fill(datastore),
                "status": datastore.status,
            }
            for datastore in reading.datastores
        ],
        "thin_pools": [
            {
                "name": pool.name,
                "volume_group": pool.volume_group,
                "node": node.name,
                "size_bytes": pool.size_bytes,
                "data_percent": pool.data_percent,
                "metadata_percent": pool.metadata_percent,
            }
            for node in reading.nodes
            for pool in node.thin_pools
        ],
        "volumes": _volumes(reading),
    }


def _backups(reading: ClusterReading) -> list[dict[str, Any]]:
    guests = {resource_id_of(guest) for guest in reading.guests}
    jobs: list[dict[str, Any]] = []
    for job in reading.backup_jobs:
        covered = (
            guests
            if job.covers_all
            else {resource_id_of(guest) for guest in reading.guests if guest.vmid in set(job.vmids)}
        )
        jobs.append(
            {
                "job_id": job.job_id,
                "comment": job.comment,
                "node": job.node,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "covers_all": job.covers_all,
                "resource_ids": sorted(covered),
                "keep_last": job.keep_last,
                "last_run_at": job.last_run_at,
                "covered": len(covered),
                "uncovered": len(guests) - len(covered),
            }
        )
    return jobs


def _summary(reading: ClusterReading) -> dict[str, Any]:
    """Return the estate summary in the endpoint's own shape.

    Read off the resources rather than off the observations. The endpoint
    summarises the estate's own health, and an observation is a detector's
    verdict — a different thing, arriving with a different feature.
    """
    resources = _resources(reading)
    by_kind: dict[str, int] = {}
    by_health: dict[str, int] = {}
    for resource in resources:
        kind = str(resource["kind"])
        health = str(resource["health"])
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_health[health] = by_health.get(health, 0) + 1
    problems = sum(count for state, count in by_health.items() if state in _PROBLEM_STATES)
    return {
        "total": len(resources),
        "captured_at": reading.captured_at,
        "by_kind": dict(sorted(by_kind.items())),
        "by_health": dict(sorted(by_health.items())),
        "by_source": {_SOURCE: len(resources)},
        "problems": problems,
        "maintenance": by_health.get("maintenance", 0),
        "absent": 0,
    }


#: What counts against an operator, as the platform counts it. Maintenance and
#: staleness are deliberately not here.
_PROBLEM_STATES: Final[frozenset[str]] = frozenset({"degraded", "unhealthy"})


def _health(
    resource: Mapping[str, Any], observations: Sequence[Observation]
) -> list[dict[str, str]]:
    mine = [item for item in observations if item.subject == resource["resource_id"]]
    if not mine:
        return [{"check": "estate", "verdict": "ok", "detail": "nothing was found about it"}]
    return [
        {"check": item.detector, "verdict": item.verdict, "detail": item.detail} for item in mine
    ]


# --- Observation -----------------------------------------------------------------


def _observations(reading: ClusterReading) -> Iterator[Observation]:
    for ordinal, observation in enumerate(_findings(reading), start=1):
        yield Observation(
            observation_id=f"obs-{ordinal:04d}",
            detector=observation[0],
            subject=observation[1],
            verdict=observation[2],
            severity=observation[3],
            observed_at=reading.captured_at,
            detail=observation[4],
            evidence=observation[5],
        )


def _findings(
    reading: ClusterReading,
) -> Iterator[tuple[str, str, str, str, str, dict[str, Any]]]:
    severity = {detector.detector_id: detector.severity for detector in DETECTORS}
    cluster = "cluster"

    quorum = reading.quorum
    if quorum.margin == 0 and quorum.expected_votes:
        yield (
            "quorum-margin-zero",
            cluster,
            "finding",
            severity["quorum-margin-zero"],
            f"{quorum.total_votes} of {quorum.quorum} required votes, so losing one node "
            f"makes the cluster filesystem read-only",
            {
                "total_votes": quorum.total_votes,
                "quorum": quorum.quorum,
                "two_node": quorum.two_node,
                "wait_for_all": quorum.wait_for_all,
            },
        )
    if quorum.device_in_membership and not quorum.device_declared:
        yield (
            "quorum-device-not-contributing",
            cluster,
            "finding",
            severity["quorum-device-not-contributing"],
            "a quorum device appears in the membership view and the configuration declares none",
            {"device_in_membership": True, "device_declared": False},
        )

    covered = _covered_resource_ids(reading)
    for job in reading.backup_jobs:
        if not job.enabled:
            yield (
                "backup-job-disabled",
                job.job_id,
                "finding",
                severity["backup-job-disabled"],
                f"{job.comment or job.job_id} exists on schedule {job.schedule} and is disabled",
                {"schedule": job.schedule, "covers_all": job.covers_all},
            )
        if job.keep_last <= SHALLOW_RETENTION_KEEP_LAST:
            yield (
                "shallow-backup-retention",
                job.job_id,
                "finding",
                severity["shallow-backup-retention"],
                f"retention is keep-last={job.keep_last}",
                {"keep_last": job.keep_last},
            )

    for guest in reading.guests:
        identifier = resource_id_of(guest)
        if identifier not in covered:
            yield (
                "guest-uncovered-by-backup",
                identifier,
                "finding",
                severity["guest-uncovered-by-backup"],
                f"{guest.name} is named by no enabled backup job",
                {"node": guest.node},
            )

    for datastore in reading.datastores:
        if datastore.status == "unknown":
            yield (
                "datastore-status-unknown",
                datastore.name,
                "unknown",
                severity["datastore-status-unknown"],
                f"{datastore.name} answers unknown, so its fill is not a number anybody has",
                {"node": datastore.node, "kind": datastore.kind},
            )
            continue
        fill = _fill(datastore)
        if fill is None:
            continue
        if fill >= DATASTORE_HIGH_PERCENT:
            yield (
                "datastore-near-full",
                datastore.name,
                "finding",
                "critical" if fill >= DATASTORE_CRITICAL_PERCENT else "high",
                f"{datastore.name} is {fill}% full",
                {"used_percent": fill, "node": datastore.node},
            )

    for node in reading.nodes:
        for volume in node.volumes:
            if volume.used_percent >= VOLUME_HIGH_PERCENT:
                subject = _subject_for_volume(reading, volume.name)
                yield (
                    "guest-volume-near-full",
                    subject,
                    "finding",
                    severity["guest-volume-near-full"],
                    f"{volume.name} is at {volume.used_percent}% of its own volume",
                    {"pool": volume.pool, "node": node.name},
                )
        for pool in node.thin_pools:
            if pool.metadata_percent >= POOL_METADATA_HIGH_PERCENT:
                yield (
                    "thin-pool-metadata-pressure",
                    pool.name,
                    "finding",
                    severity["thin-pool-metadata-pressure"],
                    f"{pool.name} metadata is at {pool.metadata_percent}% while its data "
                    f"reads {pool.data_percent}%",
                    {"node": node.name, "metadata_percent": pool.metadata_percent},
                )
        if node.failed_units:
            yield (
                "failed-systemd-units",
                node_resource_id(node.name),
                "finding",
                severity["failed-systemd-units"],
                f"{len(node.failed_units)} failed units on {node.name}",
                {"units": list(node.failed_units)},
            )
        if node.kernel_installed and node.kernel_installed != node.kernel_running:
            yield (
                "kernel-never-booted",
                node_resource_id(node.name),
                "finding",
                severity["kernel-never-booted"],
                f"{node.kernel_installed} is installed and {node.kernel_running} is running",
                {"installed": node.kernel_installed, "running": node.kernel_running},
            )
        security = sum(1 for package in node.packages if package.is_security)
        if security:
            yield (
                "security-updates-pending",
                node_resource_id(node.name),
                "finding",
                severity["security-updates-pending"],
                f"{security} security updates pending on {node.name}",
                {"pending": len(node.packages), "security": security},
            )
        if not node.bridges:
            yield (
                "bridge-absent",
                node_resource_id(node.name),
                "finding",
                severity["bridge-absent"],
                f"{node.name} has no bridge interface at all",
                {},
            )

    if not reading.replication_jobs and reading.guests:
        yield (
            "no-replication-node-local-storage",
            cluster,
            "finding",
            severity["no-replication-node-local-storage"],
            "no replication job exists while guests are on node-local storage",
            {"guests": len(reading.guests)},
        )


def _detectors(
    reading: ClusterReading, observations: Sequence[Observation]
) -> list[dict[str, Any]]:
    subjects = len(reading.guests) + len(reading.nodes)
    seen = {item.detector for item in observations}
    return [
        {
            "detector_id": detector.detector_id,
            "name": detector.name,
            "description": detector.description,
            "severity": detector.severity,
            "enabled": True,
            "signal": detector.signal,
            "subjects_covered": sum(
                1 for item in observations if item.detector == detector.detector_id
            ),
            "subjects_total": subjects,
            "last_evaluated_at": reading.captured_at,
            "last_verdict": "firing" if detector.detector_id in seen else "clear",
        }
        for detector in DETECTORS
    ]


def _incidents(
    reading: ClusterReading, observations: Sequence[Observation]
) -> Iterator[dict[str, Any]]:
    """Yield one incident per detector that found something worth waking somebody for.

    Grouped by detector rather than by subject: fifty-five guests with no backup
    is one finding about a job, not fifty-five incidents, and a console that
    showed the second would be a console nobody could read.
    """
    grouped: dict[str, list[Observation]] = {}
    for item in observations:
        if item.verdict != "finding" or item.severity not in {"critical", "high"}:
            continue
        grouped.setdefault(item.detector, []).append(item)

    names = {detector.detector_id: detector for detector in DETECTORS}
    for ordinal, (detector_id, found) in enumerate(sorted(grouped.items()), start=1):
        detector = names[detector_id]
        yield {
            "incident_id": f"inc-{ordinal:04d}",
            "title": detector.name,
            "severity": max(
                (item.severity for item in found),
                key=lambda level: ["low", "medium", "high", "critical"].index(level),
            ),
            "state": "open",
            "origin": "detector",
            "opened_at": reading.captured_at,
            "closed_at": None,
            "subjects": sorted({item.subject for item in found}),
            "detector": detector_id,
            "run_id": None,
            "team_node_id": "",
            "self_resolved": False,
            "suppressed_by": "",
            "close_reason": "",
            "summary": found[0].detail
            if len(found) == 1
            else f"{len(found)} subjects: {found[0].detail}",
        }


def _timeline(incident: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return the one entry an incident starts with, in the route's own shape.

    The actor and the cause are not decoration: every timeline entry carries
    both, because "it opened" is not an answer to the question a timeline is
    read to answer.
    """
    subjects = len(incident["subjects"])
    raised_by_alert = incident["origin"] == "alert"
    return [
        {
            "at": str(incident["opened_at"]),
            "kind": "opened",
            "actor": "system:webhook" if raised_by_alert else "system:observation",
            "cause": str(incident["summary"]),
            "detail": (
                f"{incident['detector']} delivered an alert about {subjects} target(s)"
                if raised_by_alert
                else f"{incident['detector']} found {subjects} subject(s)"
            ),
        }
    ]


def _as_json(observation: Observation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "detector": observation.detector,
        "subject": observation.subject,
        "verdict": observation.verdict,
        "severity": observation.severity,
        "observed_at": observation.observed_at,
        "detail": observation.detail,
        # Strings, for the reason ``HealthSignal.value`` is: half of what a
        # provider reports is a word, and a map that held both would be one the
        # console had to type-switch on per key.
        "evidence": {name: _as_text(value) for name, value in observation.evidence.items()},
    }


def _as_text(value: Any) -> str:
    """Return one evidence value as the string the endpoint sends."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _covered_resource_ids(reading: ClusterReading) -> set[str]:
    """Return the guests an *enabled* backup job names.

    Coverage is the question, not job count. A guest named only by a disabled
    job has no backup, and every view that lists jobs rather than coverage
    reports the opposite.
    """
    covered: set[str] = set()
    for job in reading.backup_jobs:
        if not job.enabled:
            continue
        if job.covers_all:
            return {resource_id_of(guest) for guest in reading.guests}
        named = set(job.vmids)
        covered |= {resource_id_of(guest) for guest in reading.guests if guest.vmid in named}
    return covered


def _subject_for_volume(reading: ClusterReading, volume_name: str) -> str:
    vmid = _vmid_of(volume_name)
    for guest in reading.guests:
        if guest.vmid == vmid:
            return resource_id_of(guest)
    return volume_name


def _vmid_of(volume_name: str) -> str:
    parts = volume_name.split("-")
    return parts[1] if len(parts) > 2 and parts[1].isdigit() else ""


def _fill(datastore: DatastoreReading) -> float | None:
    if datastore.used_bytes is None or not datastore.total_bytes:
        return None
    return round(datastore.used_bytes * 100.0 / datastore.total_bytes, 2)


__all__ = [
    "DATASTORE_CRITICAL_PERCENT",
    "DATASTORE_HIGH_PERCENT",
    "DETECTORS",
    "POOL_METADATA_HIGH_PERCENT",
    "SHALLOW_RETENTION_KEEP_LAST",
    "VOLUME_HIGH_PERCENT",
    "BackupJobReading",
    "ClusterReading",
    "DatastoreReading",
    "Detector",
    "GuestReading",
    "NodeReading",
    "Observation",
    "node_resource_id",
    "project",
    "resource_id_of",
]
