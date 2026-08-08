"""The dictionaries the in-memory backend keeps, and the guards every port shares.

One ``TenantState`` per organisation, held in a ``State`` that the gateway
snapshots on ``begin`` and swaps in on commit. That is what gives the fakes real
transactions rather than approximate ones: a unit of work mutates a copy, and a
unit that raises leaves the committed copy untouched — including across four
different repositories, which is what SC-001 asks for.

The guards are here rather than repeated in each fake for the reason they exist
at all. ``MAX_QUERY_PAGE_SIZE`` and ``MAX_JSONB_PAYLOAD_BYTES`` are contract, so
a caller that exceeds one gets the same error from every backend; thirteen
independent copies of that check is thirteen chances for one of them to clamp
instead of raise.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.persistence import (
    HNSW_EF_CONSTRUCTION,
    HNSW_EF_SEARCH,
    HNSW_M,
    MAX_JSONB_PAYLOAD_BYTES,
    MAX_QUERY_PAGE_SIZE,
)
from platform.persistence.errors import BoundExceeded, PayloadTooLarge
from platform.persistence.ports.approval_store import ApprovalRequest, RollbackPlan
from platform.persistence.ports.audit_repository import AuditEvent
from platform.persistence.ports.config_repository import ConfigNode, Organisation
from platform.persistence.ports.credential_store import CredentialMetadata, SecretValue
from platform.persistence.ports.episode_store import Episode, StoredStrategy
from platform.persistence.ports.estate_repository import (
    HealthTransition,
    Resource,
    ResourceReference,
    SweepRecord,
)
from platform.persistence.ports.identity_repository import ApiToken, RoleBinding, User
from platform.persistence.ports.incident_store import Incident, TimelineEntry
from platform.persistence.ports.knowledge_store import KnowledgeChunk, KnowledgeDocument
from platform.persistence.ports.remediation_ledger import RecurringProblem, RemediationOutcome
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    ToolCallRecord,
    TraceEventRecord,
    TurnRecord,
)
from platform.persistence.ports.schedule_store import JobClaim, ScheduledJob
from platform.persistence.ports.session_store import SessionRecord
from platform.persistence.ports.signal_store import Signal
from platform.persistence.ports.topology_graph import TopologyEdge, TopologyNode
from platform.persistence.ports.vector_index import IndexDescriptor, VectorRecord

#: Identifies an edge: two endpoints and a kind. Two services can be related in
#: more than one way — a service both calls an API and reads its database — and
#: collapsing those onto one edge would lose the distinction a dependency graph
#: exists to record.
EdgeKey = tuple[str, str, str]

#: Identifies a synthesised playbook within one organisation: the team, the
#: issue type, and the normalised component key. The team is in the key rather
#: than beside it because a playbook is a team's accumulated experience, and one
#: team reading another's would be the cross-team leak FR-018 exists to prevent.
StrategyKey = tuple[str, str, str]

#: Identifies one reference from a resource to a run or an incident: the
#: resource, what kind of thing referenced it, and which one. Keyed rather than
#: appended so that linking the same run twice is one row — a run that touched a
#: resource in nine turns touched it once.
ReferenceKey = tuple[str, str, str]


def check_limit(limit: int, *, parameter: str = "limit") -> int:
    """Return ``limit``, or raise if it exceeds the page bound.

    Raising rather than clamping, because a caller that asked for 500 and
    received 200 has no way to tell that from there being 200.
    """
    if limit > MAX_QUERY_PAGE_SIZE:
        raise BoundExceeded(
            parameter=parameter,
            requested=limit,
            limit=MAX_QUERY_PAGE_SIZE,
            constant="MAX_QUERY_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"{parameter} must be at least 1, got {limit}.")
    return limit


def check_payload(payload: Mapping[str, Any], *, kind: str) -> Mapping[str, Any]:
    """Return ``payload``, or raise if its JSON form exceeds the row bound."""
    size = len(json.dumps(payload).encode("utf-8"))
    if size > MAX_JSONB_PAYLOAD_BYTES:
        raise PayloadTooLarge(kind=kind, size_bytes=size, limit_bytes=MAX_JSONB_PAYLOAD_BYTES)
    return payload


@dataclass
class VectorGeneration:
    """One population of an index, written by one embedding model."""

    number: int
    model: str
    dimension: int
    records: dict[str, VectorRecord] = field(default_factory=dict)


@dataclass
class VectorNamespace:
    """One declared index, and every generation it has held.

    Generations are kept rather than replaced so that ``activate_generation``
    is a pointer move. A re-embed that had to delete as it went would leave
    search reading a half-empty index for as long as the re-embed took, which
    is the downtime FR-014 exists to avoid.
    """

    name: str
    active: int
    generations: dict[int, VectorGeneration] = field(default_factory=dict)
    m: int = HNSW_M
    ef_construction: int = HNSW_EF_CONSTRUCTION
    ef_search: int = HNSW_EF_SEARCH
    created_at: datetime | None = None

    @property
    def active_generation(self) -> VectorGeneration:
        """Return the generation searches read."""
        return self.generations[self.active]

    def descriptor(self) -> IndexDescriptor:
        """Return the public description of this index's active generation."""
        generation = self.active_generation
        return IndexDescriptor(
            namespace=self.name,
            model=generation.model,
            dimension=generation.dimension,
            generation=generation.number,
            m=self.m,
            ef_construction=self.ef_construction,
            ef_search=self.ef_search,
            created_at=self.created_at,
        )


@dataclass
class StoredCredential:
    """A credential as the fake holds it.

    The secret is in a ``SecretValue`` and the field is out of the ``repr``, so
    neither a debugger nor a log line that rendered this object would show it.
    The fake stores plaintext because there is no rest to encrypt at — FR-018's
    at-rest encryption is a property of the Postgres backend and is tested
    there. What the *port contract* can require of any backend, and does, is
    that nothing but ``reveal`` ever returns it.
    """

    metadata: CredentialMetadata
    secret: SecretValue = field(repr=False)


@dataclass
class TenantState:
    """Everything one organisation owns."""

    config_nodes: dict[str, ConfigNode] = field(default_factory=dict)
    users: dict[str, User] = field(default_factory=dict)
    tokens: dict[str, ApiToken] = field(default_factory=dict)
    role_bindings: dict[str, RoleBinding] = field(default_factory=dict)
    audit_events: dict[str, AuditEvent] = field(default_factory=dict)
    runs: dict[str, AgentRun] = field(default_factory=dict)
    turns: dict[str, TurnRecord] = field(default_factory=dict)
    tool_calls: dict[str, ToolCallRecord] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    trace_events: dict[str, TraceEventRecord] = field(default_factory=dict)
    sessions: dict[str, SessionRecord] = field(default_factory=dict)
    episodes: dict[str, Episode] = field(default_factory=dict)
    strategies: dict[StrategyKey, StoredStrategy] = field(default_factory=dict)
    vector_indexes: dict[str, VectorNamespace] = field(default_factory=dict)
    documents: dict[str, KnowledgeDocument] = field(default_factory=dict)
    chunks: dict[str, KnowledgeChunk] = field(default_factory=dict)
    approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    rollback_plans: dict[str, RollbackPlan] = field(default_factory=dict)
    executed_rollbacks: dict[str, tuple[int, ...]] = field(default_factory=dict)
    jobs: dict[str, ScheduledJob] = field(default_factory=dict)
    credentials: dict[str, StoredCredential] = field(default_factory=dict)
    topology_nodes: dict[str, TopologyNode] = field(default_factory=dict)
    topology_edges: dict[EdgeKey, TopologyEdge] = field(default_factory=dict)
    resources: dict[str, Resource] = field(default_factory=dict)
    health_transitions: dict[str, HealthTransition] = field(default_factory=dict)
    resource_references: dict[ReferenceKey, ResourceReference] = field(default_factory=dict)
    sweeps: dict[str, SweepRecord] = field(default_factory=dict)
    #: Keyed by the derived signal id rather than appended to, which is what
    #: makes a retried poll one sample instead of two.
    signals: dict[str, Signal] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    incident_timeline: dict[str, TimelineEntry] = field(default_factory=dict)
    #: Keyed by the action, so an executor that retried writes one obligation
    #: rather than two verifications of one change.
    remediation_outcomes: dict[str, RemediationOutcome] = field(default_factory=dict)
    remediation_problems: dict[str, RecurringProblem] = field(default_factory=dict)


@dataclass
class State:
    """The whole in-memory store.

    ``topology_available`` is a lever, not a bug. FR-002 says a deployment
    without Apache AGE degrades rather than crashes, and the only way to hold a
    contract suite to that is to be able to turn topology off and watch what
    the other eleven ports do. A real backend discovers this by probing; the
    fake is told.
    """

    organisations: dict[str, Organisation] = field(default_factory=dict)
    tenants: dict[str, TenantState] = field(default_factory=dict)
    claims: dict[str, JobClaim] = field(default_factory=dict)
    topology_available: bool = True
    topology_unavailable_reason: str = "The Apache AGE extension is not installed."

    def tenant(self, org_id: str) -> TenantState:
        """Return the state for ``org_id``, creating it on first use."""
        return self.tenants.setdefault(org_id, TenantState())


__all__ = [
    "EdgeKey",
    "ReferenceKey",
    "State",
    "StoredCredential",
    "StrategyKey",
    "TenantState",
    "VectorGeneration",
    "VectorNamespace",
    "check_limit",
    "check_payload",
]
