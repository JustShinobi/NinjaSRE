"""Loading the demonstration deployment into the real database, and taking it out.

Into the real database, through the ordinary ports, so a console reading the
estate the ordinary way sees it. Anything else would be a second rendering path
that only demo mode exercises — and a demonstration that goes through code
nobody else runs is a demonstration of that code.

Three properties hold the whole thing together.

**It lives in its own tenant.** ``org_id`` is on every row of every table, which
makes it a label that a record kind added next year inherits for free, makes
removal one operation rather than a sweep of thirteen ports, and makes FR-020's
refusal structural: seeding over real data means seeding over *this tenant's*
real data, which nothing else has any reason to be in.

**It refuses to seed over real data.** Anything already in the demonstration
tenant that is not labelled as a demonstration stops the seed and says how to
override it. The one thing worse than an empty console is one where a real
incident and a fictional one sit side by side.

**It removes completely.** Removal deletes the tenant, and ``demonstration_residue``
then sweeps every organisation for anything still carrying the label. That sweep
is what SC-009 is; the removal is only the part that makes it come back empty.

One thing this deliberately does not seed: **audit events**. The demonstration's
history is in its incident timelines and its run traces, which is where the
console shows it. Audit is append-only by constitutional design and exempt from
retention deletion, and the schema's audit foreign key restricts rather than
cascades — so seeded demonstration audit events would make the tenant
undeletable and would contaminate the audit trail permanently. That is exactly
the contamination FR-017 to FR-020 exist to prevent, so the audit history is the
one part of the scenario that stays in the mock plane.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from platform.observability.logging import get_logger
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.episode_store import Episode, EpisodeOutcome
from platform.persistence.ports.estate_repository import EstateQuery, Resource, ResourceHealth
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    TimelineEntry,
    TimelineKind,
)
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    RunStatus,
    ToolCallRecord,
    ToolCallStatus,
    TurnRecord,
)
from platform.persistence.ports.topology_graph import EdgeKind, NodeKind, TopologyEdge, TopologyNode
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.startup.demo.dataset import (
    CLUSTER_RESOURCE_ID,
    CLUSTER_RESOURCE_KIND,
    DemoDataset,
    load_dataset,
)
from platform.startup.demo.labels import (
    is_demonstration,
    is_demonstration_text,
    labelled,
    labelled_text,
)

logger = get_logger(__name__)

#: The capture's vocabulary, and this schema's. They differ in three words and
#: mapping them explicitly is what stops a silent ``KeyError`` turning into an
#: empty runs screen.
_RUN_STATUS: Mapping[str, RunStatus] = {
    "succeeded": RunStatus.COMPLETED,
    "completed": RunStatus.COMPLETED,
    "running": RunStatus.RUNNING,
    "failed": RunStatus.FAILED,
    "cancelled": RunStatus.CANCELLED,
    "awaiting_approval": RunStatus.SUSPENDED,
    "suspended": RunStatus.SUSPENDED,
    "interrupted": RunStatus.INTERRUPTED,
}

_EPISODE_OUTCOME: Mapping[str, EpisodeOutcome] = {
    "resolved": EpisodeOutcome.RESOLVED,
    "mitigated": EpisodeOutcome.MITIGATED,
    "acknowledged": EpisodeOutcome.MITIGATED,
    "unresolved": EpisodeOutcome.INCONCLUSIVE,
    "inconclusive": EpisodeOutcome.INCONCLUSIVE,
    "false_positive": EpisodeOutcome.FALSE_POSITIVE,
}

#: What a datastore, a thin pool and a backup job are called in the estate.
KIND_DATASTORE = "datastore"
KIND_THIN_POOL = "thin-pool"
KIND_BACKUP_JOB = "backup-job"

#: The source every one of these came from. One value, because the capture is of
#: one deployment and pretending otherwise would be inventing a second.
DEMO_SOURCE = "proxmox"


class DemoRefused(RuntimeError):
    """Demo mode will not seed over data somebody depends on (FR-020)."""

    def __init__(self, organisation_id: str, records: Sequence[str]) -> None:
        listed = ", ".join(records[:5]) + (" and others" if len(records) > 5 else "")
        super().__init__(
            f"{organisation_id} already holds {len(records)} record(s) that are not "
            f"demonstration data ({listed}). Seeding would put a fictional estate beside a "
            f"real one and nothing in the console would distinguish them. Pass --force if "
            f"this really is a deployment you are willing to mix."
        )
        self.organisation_id = organisation_id
        self.records = tuple(records)


@dataclass(frozen=True, slots=True)
class SeedReport:
    """What the seeder loaded, by kind."""

    organisation_id: str
    counts: Mapping[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    #: Whether it went ahead over data it would otherwise have refused.
    forced: bool = False

    @property
    def total(self) -> int:
        """Return how many records were written altogether."""
        return sum(self.counts.values())

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a surface reports."""
        return {
            "organisation_id": self.organisation_id,
            "counts": dict(self.counts),
            "total": self.total,
            "duration_seconds": round(self.duration_seconds, 3),
            "forced": self.forced,
        }

    def summary(self) -> str:
        """Return the line a terminal prints."""
        listed = ", ".join(f"{count} {kind}" for kind, count in sorted(self.counts.items()))
        return (
            f"demonstration data loaded into {self.organisation_id} in "
            f"{self.duration_seconds:.1f}s: {listed}"
        )


@dataclass(frozen=True, slots=True)
class RemovalReport:
    """What removal took out, and whether there was anything to take."""

    organisation_id: str
    removed: bool
    counts: Mapping[str, int] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a surface reports."""
        return {
            "organisation_id": self.organisation_id,
            "removed": self.removed,
            "counts": dict(self.counts),
        }

    def summary(self) -> str:
        """Return the line a terminal prints."""
        if not self.removed:
            return f"no demonstration data in {self.organisation_id}; nothing to remove"
        total = sum(self.counts.values())
        return f"removed {total} demonstration record(s) and the {self.organisation_id} tenant"


def _instant(value: Any) -> datetime | None:
    """Return an ISO timestamp as a datetime, or ``None`` when there is none."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _required_instant(value: Any) -> datetime:
    """Return an ISO timestamp, falling back to the epoch's UTC rather than now.

    A fixed fallback rather than ``datetime.now``: two seeds of the same dataset
    have to produce the same rows, or a visual-regression baseline captured
    against one of them is a photograph of a moment.
    """
    return _instant(value) or datetime(1970, 1, 1, tzinfo=UTC)


# --- Building the estate -----------------------------------------------------------


def _guest_resources(dataset: DemoDataset) -> Iterator[Resource]:
    """Yield the containers, virtual machines and hosts the capture recorded."""
    for row in dataset.guests:
        health = ResourceHealth(str(row.get("health", ResourceHealth.UNKNOWN)))
        yield Resource(
            resource_id=str(row["resource_id"]),
            kind=str(row.get("kind", "unknown")),
            source=str(row.get("source", DEMO_SOURCE)),
            native_id=str(row.get("native_id", row["resource_id"])),
            display_name=str(row.get("display_name", "")),
            parent_id=str(row["parent_id"]) if row.get("parent_id") else None,
            attributes=labelled(
                _mapping(row.get("attributes")),
                explanation=str(row.get("explanation", "")),
            ),
            labels=tuple(str(label) for label in row.get("labels", ())),
            health=health,
            first_seen_at=_instant(row.get("first_seen_at")),
            last_seen_at=_instant(row.get("last_seen_at")),
        )


def _host_detail(dataset: DemoDataset) -> Mapping[str, Mapping[str, Any]]:
    """Return the extra the host read adds to a resource the guest read already has.

    The two reads describe the same hosts: ``estate-resources`` has them as
    resources, ``estate-nodes`` has their kernel, their failed units and their
    quorum votes. Merged rather than seeded twice, because two rows for one host
    is the coherence failure the dataset is checked for.
    """
    return {
        str(row["node_id"]): {
            key: value for key, value in row.items() if key not in {"node_id", "name"}
        }
        for row in dataset.nodes
        if row.get("node_id")
    }


def _storage_resources(dataset: DemoDataset) -> Iterator[Resource]:
    """Yield the datastores and thin pools the guests live on."""
    for row in dataset.datastores:
        name = str(row.get("name", ""))
        if not name:
            continue
        used = float(row.get("used_percent") or 0.0)
        yield Resource(
            resource_id=name,
            kind=KIND_DATASTORE,
            source=DEMO_SOURCE,
            native_id=name,
            display_name=name,
            parent_id=str(row["node"]) if row.get("node") else None,
            attributes=labelled(row),
            health=_storage_health(str(row.get("status", "")), used),
        )
    for row in dataset.thin_pools:
        name = str(row.get("name", ""))
        if not name:
            continue
        yield Resource(
            resource_id=name,
            kind=KIND_THIN_POOL,
            source=DEMO_SOURCE,
            native_id=name,
            display_name=name,
            attributes=labelled(row),
            health=ResourceHealth.HEALTHY,
        )


def _storage_health(status: str, used_percent: float) -> ResourceHealth:
    """Return what a datastore's reported status and fill mean for its health."""
    if status and status != "available":
        # Two of this capture's datastores answer ``unknown``, which is the
        # awkwardness the dataset exists to preserve: not a failure, not a pass.
        return ResourceHealth.UNKNOWN
    if used_percent >= 90:
        return ResourceHealth.UNHEALTHY
    if used_percent >= 80:
        return ResourceHealth.DEGRADED
    return ResourceHealth.HEALTHY


def _backup_resources(dataset: DemoDataset) -> Iterator[Resource]:
    """Yield the backup jobs, including the one that exists and is disabled."""
    for row in dataset.backup_jobs:
        job_id = str(row.get("job_id", ""))
        if not job_id:
            continue
        enabled = bool(row.get("enabled", False))
        yield Resource(
            resource_id=job_id,
            kind=KIND_BACKUP_JOB,
            source=DEMO_SOURCE,
            native_id=job_id,
            display_name=str(row.get("comment") or job_id),
            parent_id=str(row["node"]) if row.get("node") else None,
            attributes=labelled(row),
            health=ResourceHealth.HEALTHY if enabled else ResourceHealth.UNHEALTHY,
        )


def _cluster_resource(dataset: DemoDataset) -> Resource:
    """Return the cluster, derived from its own hosts' quorum arithmetic.

    Derived rather than invented. Every number here — the votes each host holds,
    the votes the cluster expects, the members' names — is read off the host
    rows the capture recorded, which is what makes the resulting resource part
    of the same deployment rather than a fifth thing somebody made up.
    """
    votes = sum(int(row.get("quorum_votes", 0)) for row in dataset.nodes)
    expected = max((int(row.get("expected_votes", 0)) for row in dataset.nodes), default=0)
    members = tuple(str(row.get("name", "")) for row in dataset.nodes)
    return Resource(
        resource_id=CLUSTER_RESOURCE_ID,
        kind=CLUSTER_RESOURCE_KIND,
        source=DEMO_SOURCE,
        native_id=CLUSTER_RESOURCE_ID,
        display_name="cluster",
        attributes=labelled(
            quorum_votes=votes,
            expected_votes=expected,
            members=list(members),
            margin=votes - expected,
        ),
        # Quorum with no margin: losing one host makes the cluster filesystem
        # read-only. Degraded rather than healthy is the whole point of the
        # scenario, and it follows from the arithmetic rather than from a flag.
        health=ResourceHealth.HEALTHY if votes > expected else ResourceHealth.DEGRADED,
    )


def estate_of(dataset: DemoDataset) -> tuple[Resource, ...]:
    """Return every resource the demonstration estate holds, deduplicated."""
    detail = _host_detail(dataset)
    by_id: dict[str, Resource] = {}

    for resource in _guest_resources(dataset):
        extra = detail.get(resource.resource_id)
        if extra:
            resource = Resource(
                **{
                    **{
                        name: getattr(resource, name)
                        for name in (
                            "resource_id",
                            "kind",
                            "source",
                            "native_id",
                            "display_name",
                            "parent_id",
                            "labels",
                            "health",
                            "first_seen_at",
                            "last_seen_at",
                        )
                    },
                    "attributes": labelled({**resource.attributes, **extra}),
                }
            )
        by_id[resource.resource_id] = resource

    for resource in (*_storage_resources(dataset), *_backup_resources(dataset)):
        by_id.setdefault(resource.resource_id, resource)

    cluster = _cluster_resource(dataset)
    by_id.setdefault(cluster.resource_id, cluster)
    return tuple(by_id[key] for key in sorted(by_id))


# --- Seeding -------------------------------------------------------------------------


async def seed_demonstration(
    gateway: PersistenceGateway,
    *,
    dataset: DemoDataset | None = None,
    organisation_id: str | None = None,
    force: bool = False,
) -> SeedReport:
    """Load the demonstration deployment, and return what was loaded.

    Idempotent: every write is an upsert keyed by the dataset's own identifiers,
    so seeding twice produces the same rows rather than twice as many.

    Raises:
        DemoRefused: the tenant already holds records that are not labelled as
            demonstration data, and ``force`` was not set.
    """
    data = dataset if dataset is not None else load_dataset()
    tenant = organisation_id or data.organisation_id
    started = time.perf_counter()
    scope = TenantScope(org_id=tenant)

    created = await _ensure_tenant(gateway, tenant, data.organisation_name)
    if not created:
        intruders = await _non_demonstration_records(gateway, scope)
        if intruders and not force:
            raise DemoRefused(tenant, intruders)

    counts = {
        "config_nodes": await _seed_config(gateway, scope, data),
        "resources": await _seed_estate(gateway, scope, data),
        "topology_nodes": await _seed_topology(gateway, scope, data),
        "incidents": await _seed_incidents(gateway, scope, data),
        "runs": await _seed_runs(gateway, scope, data),
        "turns": await _seed_turns(gateway, scope, data),
        "episodes": await _seed_episodes(gateway, scope, data),
        "approvals": await _seed_approvals(gateway, scope, data),
    }

    report = SeedReport(
        organisation_id=tenant,
        counts=counts,
        duration_seconds=time.perf_counter() - started,
        forced=force and not created,
    )
    logger.info("demo.seeded", organisation_id=tenant, total=report.total)
    return report


async def _ensure_tenant(gateway: PersistenceGateway, organisation_id: str, name: str) -> bool:
    """Create the demonstration organisation, returning whether it was new."""
    async with gateway.begin_system() as system:
        if await system.orgs.get_organisation(organisation_id) is not None:
            return False
        await system.orgs.create_organisation(organisation_id, name or organisation_id)
    return True


async def _non_demonstration_records(
    gateway: PersistenceGateway, scope: TenantScope
) -> tuple[str, ...]:
    """Return identifiers of anything in the tenant that is not a demonstration.

    The estate and the run trace are the two an operator would actually have put
    there — a tenant with real resources or real runs in it is a tenant in use,
    whatever else it holds.
    """
    async with gateway.begin(scope) as uow:
        resources = await uow.estate.query(EstateQuery(limit=200, include_absent=True))
        runs = await uow.run_traces.list_runs(limit=50)
        incidents = await uow.incidents.query(IncidentQuery(limit=50))

    found = [
        resource.resource_id for resource in resources if not is_demonstration(resource.attributes)
    ]
    found.extend(run.run_id for run in runs if not is_demonstration(run.metadata))
    found.extend(
        incident.incident_id
        for incident in incidents
        if not any(is_demonstration_text(subject.evidence) for subject in incident.subjects)
    )
    return tuple(sorted(found))


async def _seed_config(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write the organisation tree, parents before children."""
    rows = [row for row in dataset.config_nodes if row.get("parent_id")]
    written = 0
    async with gateway.begin(scope) as uow:
        for row in sorted(rows, key=lambda node: _depth(node, dataset)):
            node_id = str(row["node_id"])
            existing = await uow.config.get(node_id)
            await uow.config.upsert(
                ConfigNode(
                    node_id=node_id,
                    kind=_config_kind(str(row.get("kind", "team"))),
                    name=str(row.get("name", node_id)),
                    parent_id=str(row["parent_id"]),
                    values=labelled(),
                    version=existing.version if existing is not None else 0,
                )
            )
            written += 1
    return written


def _depth(row: Mapping[str, Any], dataset: DemoDataset) -> int:
    """Return how far a config node is from the root, for insertion order."""
    parents = {str(node["node_id"]): node.get("parent_id") for node in dataset.config_nodes}
    depth = 0
    current = row.get("parent_id")
    while current and depth < len(parents):
        current = parents.get(str(current))
        depth += 1
    return depth


def _config_kind(value: str) -> ConfigNodeKind:
    """Return the node kind, defaulting to a team for anything unrecognised."""
    try:
        return ConfigNodeKind(value)
    except ValueError:
        return ConfigNodeKind.TEAM


async def _seed_estate(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write the estate, parentless resources first so a parent always exists."""
    resources = estate_of(dataset)
    ordered = sorted(resources, key=lambda resource: resource.parent_id is not None)
    async with gateway.begin(scope) as uow:
        for resource in ordered:
            await uow.estate.upsert(resource)
    return len(resources)


async def _seed_topology(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write the service graph and the edges between its nodes."""
    written = 0
    async with gateway.begin(scope) as uow:
        if not (await uow.topology.availability()).available:
            # A deployment without the graph extension degrades rather than
            # failing to seed: an investigation with no blast radius is worse,
            # not impossible, and the same is true of a demonstration.
            return 0
        for row in dataset.topology_nodes:
            await uow.topology.upsert_node(
                TopologyNode(
                    node_id=str(row["node_id"]),
                    kind=_node_kind(str(row.get("kind", "service"))),
                    name=str(row.get("name", row["node_id"])),
                    properties=labelled(_mapping(row.get("properties"))),
                )
            )
            written += 1
        for origin, target in dataset.topology_edges:
            await uow.topology.upsert_edge(
                TopologyEdge(
                    from_node_id=origin,
                    to_node_id=target,
                    kind=EdgeKind.DEPENDS_ON,
                    properties=labelled(),
                )
            )
    return written


def _node_kind(value: str) -> NodeKind:
    """Return the topology kind, falling back to a plain resource."""
    try:
        return NodeKind(value)
    except ValueError:
        return NodeKind.RESOURCE


async def _seed_incidents(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write the incidents, and the timeline of the one the capture detailed."""
    written = 0
    detailed = str(dataset.detailed_incident.get("incident_id", ""))
    async with gateway.begin(scope) as uow:
        for row in dataset.incidents:
            incident_id = str(row["incident_id"])
            await uow.incidents.upsert(
                Incident(
                    incident_id=incident_id,
                    correlation_key=f"{row.get('detector', 'demo')}:{incident_id}",
                    title=str(row.get("title", incident_id)),
                    summary=str(row.get("summary", "")),
                    origin=_origin(str(row.get("origin", "detector"))),
                    origin_id=str(row.get("detector", "demonstration")),
                    severity=str(row.get("severity", "warning")),
                    state=_incident_state(str(row.get("state", "open"))),
                    opened_at=_required_instant(row.get("opened_at")),
                    closed_at=_instant(row.get("closed_at")),
                    subjects=tuple(
                        IncidentSubject(
                            resource_id=str(subject),
                            detail=str(row.get("summary", "")),
                            # ``evidence`` is the only structured column an
                            # incident has. Stamped so an incident exported out
                            # of its tenant still says what it is.
                            evidence=labelled_text(),
                        )
                        for subject in row.get("subjects", ())
                    ),
                    run_ids=(str(row["run_id"]),) if row.get("run_id") else (),
                    close_reason=str(row.get("close_reason", "")),
                    self_resolved=bool(row.get("self_resolved", False)),
                    suppressed_by=str(row.get("suppressed_by", "")),
                )
            )
            written += 1

        if detailed:
            await uow.incidents.append(
                tuple(
                    TimelineEntry(
                        entry_id=f"{detailed}-{index}",
                        incident_id=detailed,
                        kind=_timeline_kind(str(entry.get("kind", "opened"))),
                        at=_required_instant(entry.get("at")),
                        actor=str(entry.get("actor", "system:observation")),
                        cause=str(entry.get("cause", "")),
                        detail=str(entry.get("detail", "")),
                    )
                    for index, entry in enumerate(dataset.timeline)
                )
            )
    return written


def _origin(value: str) -> IncidentOrigin:
    """Return what raised an incident, defaulting to a detector."""
    try:
        return IncidentOrigin(value)
    except ValueError:
        return IncidentOrigin.DETECTOR


def _incident_state(value: str) -> IncidentState:
    """Return an incident's state, defaulting to open."""
    try:
        return IncidentState(value)
    except ValueError:
        return IncidentState.OPEN


def _timeline_kind(value: str) -> TimelineKind:
    """Return a timeline entry's kind, defaulting to the entry that opens one."""
    try:
        return TimelineKind(value)
    except ValueError:
        return TimelineKind.OPENED


async def _seed_runs(gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset) -> int:
    """Write the investigations, completed and in flight."""
    async with gateway.begin(scope) as uow:
        for row in dataset.runs:
            run_id = str(row["run_id"])
            if await uow.run_traces.get_run(run_id) is not None:
                continue
            await uow.run_traces.start_run(
                AgentRun(
                    run_id=run_id,
                    trigger=str(row.get("trigger", "demonstration")),
                    status=_RUN_STATUS.get(str(row.get("status", "")), RunStatus.COMPLETED),
                    started_at=_instant(row.get("started_at")),
                    finished_at=_instant(row.get("finished_at")),
                    summary=str(row.get("summary", "")) or None,
                    metadata=labelled(),
                )
            )
    return len(dataset.runs)


async def _seed_turns(gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset) -> int:
    """Write the transcript of the run the capture replayed, and its tool calls."""
    run_id = dataset.replayed_run_id
    if not run_id:
        return 0
    async with gateway.begin(scope) as uow:
        existing = {turn.turn_id for turn in await uow.run_traces.turns_for_run(run_id)}
        for row in dataset.replay_turns:
            turn_id = str(row["turn_id"])
            if turn_id in existing:
                continue
            await uow.run_traces.record_turn(
                TurnRecord(
                    turn_id=turn_id,
                    run_id=run_id,
                    index=int(row.get("index", 0)),
                    payload=labelled(
                        text=str(row.get("selection_rationale", "")),
                        model=str(row.get("model", "")),
                    ),
                )
            )
            for call in row.get("calls", ()):
                await uow.run_traces.record_tool_call(
                    ToolCallRecord(
                        call_id=str(call["call_id"]),
                        run_id=run_id,
                        turn_id=turn_id,
                        tool_name=str(call.get("name", "unknown")),
                        status=_call_status(str(call.get("status", "succeeded"))),
                        arguments=labelled(duration_ms=call.get("duration_ms")),
                        error=call.get("error"),
                    )
                )
    return len(dataset.replay_turns)


def _call_status(value: str) -> ToolCallStatus:
    """Return a tool call's status, defaulting to success."""
    try:
        return ToolCallStatus(value)
    except ValueError:
        return ToolCallStatus.SUCCEEDED


async def _seed_episodes(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write what the runs taught the deployment."""
    async with gateway.begin(scope) as uow:
        for row in dataset.episodes:
            await uow.episodes.save(
                Episode(
                    episode_id=str(row["episode_id"]),
                    title=str(row.get("title", "")),
                    summary=str(row.get("summary", "")),
                    signature=str(row.get("title", row["episode_id"])).lower().replace(" ", "-"),
                    outcome=_EPISODE_OUTCOME.get(
                        str(row.get("outcome", "")), EpisodeOutcome.INCONCLUSIVE
                    ),
                    run_id=str(row["run_id"]) if row.get("run_id") else None,
                    occurred_at=_instant(row.get("occurred_at")),
                    components=tuple(str(part) for part in row.get("components", ())),
                    metadata=labelled(),
                )
            )
    return len(dataset.episodes)


async def _seed_approvals(
    gateway: PersistenceGateway, scope: TenantScope, dataset: DemoDataset
) -> int:
    """Write the decisions waiting on a person, each with its rollback plan."""
    async with gateway.begin(scope) as uow:
        for row in dataset.approvals:
            approval_id = str(row["approval_id"])
            if await uow.approvals.get_request(approval_id) is None:
                await uow.approvals.create_request(
                    ApprovalRequest(
                        approval_id=approval_id,
                        run_id=str(row.get("run_id", "")),
                        action=str(row.get("action", "")),
                        side_effect_level=str(row.get("side_effect_level", "write")),
                        summary=str(row.get("summary", "")),
                        requested_at=_required_instant(row.get("requested_at")),
                        expires_at=_required_instant(row.get("expires_at")),
                        arguments=labelled(_mapping(row.get("arguments"))),
                        state=_approval_state(str(row.get("state", "pending"))),
                    )
                )
            plan = row.get("rollback_plan")
            if (
                isinstance(plan, Mapping)
                and await uow.approvals.rollback_plan_for(approval_id) is None
            ):
                await uow.approvals.store_rollback_plan(
                    RollbackPlan(
                        plan_id=str(plan.get("plan_id", f"{approval_id}-plan")),
                        approval_id=approval_id,
                        steps=tuple(
                            RollbackStep(
                                ordinal=int(step.get("ordinal", index + 1)),
                                description=str(step.get("description", "")),
                                capability=str(step.get("capability", "")),
                                arguments=labelled(_mapping(step.get("arguments"))),
                            )
                            for index, step in enumerate(plan.get("steps", ()))
                        ),
                        notes=str(plan.get("notes", "")) or None,
                    )
                )
    return len(dataset.approvals)


def _approval_state(value: str) -> ApprovalState:
    """Return an approval's state, defaulting to pending."""
    try:
        return ApprovalState(value)
    except ValueError:
        return ApprovalState.PENDING


def _mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a plain mapping, or an empty one."""
    return dict(value) if isinstance(value, Mapping) else {}


# --- Removal --------------------------------------------------------------------------


async def remove_demonstration(
    gateway: PersistenceGateway, *, organisation_id: str | None = None
) -> RemovalReport:
    """Remove every trace of the demonstration, in one action (FR-019).

    Counts first, then deletes the tenant. The counts are what the report says
    was removed, and taking them after the delete would mean reporting zero for
    a successful removal.
    """
    tenant = organisation_id or load_dataset().organisation_id
    async with gateway.begin_system() as system:
        if await system.orgs.get_organisation(tenant) is None:
            return RemovalReport(organisation_id=tenant, removed=False)

    scope = TenantScope(org_id=tenant)
    async with gateway.begin(scope) as uow:
        counts = {
            "resources": len(await uow.estate.query(EstateQuery(limit=500, include_absent=True))),
            "incidents": len(await uow.incidents.query(IncidentQuery(limit=200))),
            "runs": len(await uow.run_traces.list_runs(limit=200)),
            "episodes": len(await uow.episodes.list_recent(limit=200)),
            "approvals": len(await uow.approvals.list_pending(limit=200)),
        }

    async with gateway.begin_system() as system:
        await system.orgs.delete_organisation(tenant)

    logger.info("demo.removed", organisation_id=tenant)
    return RemovalReport(organisation_id=tenant, removed=True, counts=counts)


async def demonstration_residue(gateway: PersistenceGateway) -> tuple[str, ...]:
    """Return every demonstration record still in the store, anywhere.

    SC-009's sweep. It walks every organisation rather than the demonstration
    one, because "leaving nothing behind" is a claim about the store and not
    about one tenant — a record copied elsewhere before removal would satisfy
    the narrower reading and fail the one that matters.
    """
    residue: list[str] = []
    async with gateway.begin_system() as system:
        organisations = await system.orgs.list_organisations()

    for organisation in organisations:
        scope = TenantScope(org_id=organisation.org_id)
        async with gateway.begin(scope) as uow:
            for resource in await uow.estate.query(EstateQuery(limit=500, include_absent=True)):
                if is_demonstration(resource.attributes):
                    residue.append(f"{organisation.org_id}/resource/{resource.resource_id}")
            for run in await uow.run_traces.list_runs(limit=200):
                if is_demonstration(run.metadata):
                    residue.append(f"{organisation.org_id}/run/{run.run_id}")
            for episode in await uow.episodes.list_recent(limit=200):
                if is_demonstration(episode.metadata):
                    residue.append(f"{organisation.org_id}/episode/{episode.episode_id}")
            for approval in await uow.approvals.list_pending(limit=200):
                if is_demonstration(approval.arguments):
                    residue.append(f"{organisation.org_id}/approval/{approval.approval_id}")
            for incident in await uow.incidents.query(IncidentQuery(limit=200)):
                if any(is_demonstration_text(subject.evidence) for subject in incident.subjects):
                    residue.append(f"{organisation.org_id}/incident/{incident.incident_id}")
            root = await uow.config.root()
            for child in await uow.config.children(root.node_id):
                if is_demonstration(child.values):
                    residue.append(f"{organisation.org_id}/config/{child.node_id}")
    return tuple(sorted(residue))


__all__ = [
    "DEMO_SOURCE",
    "KIND_BACKUP_JOB",
    "KIND_DATASTORE",
    "KIND_THIN_POOL",
    "DemoRefused",
    "RemovalReport",
    "SeedReport",
    "demonstration_residue",
    "estate_of",
    "remove_demonstration",
    "seed_demonstration",
]
