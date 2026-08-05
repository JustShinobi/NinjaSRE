"""The twelve repository ports, and the unit of work that composes them.

This package is the whole export surface of NinjaSRE's storage layer. Everything
above tier 3 imports from here and from nowhere else in ``persistence/``: the
Postgres implementation, the in-memory fakes, and any future backend are
details, and a caller that named one would be the reason the second could not be
written.

The twelve, and what each owns:

===========================  ==================================================
``ConfigRepository``         the org/team/service hierarchy and its config
``IdentityRepository``       users, token hashes, role bindings
``AuditRepository``          append-only audit events
``RunTraceStore``            runs, turns, tool calls, evidence
``SessionStore``             resumable session state
``EpisodeStore``             episodic memory
``VectorIndex``              embeddings and similarity search
``TopologyGraph``            service topology, nine bounded traversals
``KnowledgeStore``           documents and retrievable chunks
``ApprovalStore``            approvals and rollback plans
``ScheduleStore``            scheduled job definitions
``CredentialStore``          encrypted credentials
===========================  ==================================================

They are reached through ``UnitOfWork``, which binds all twelve to one
transaction and one tenant. Read ``transaction`` first: it explains why the
ports take no organisation argument, and that fact is the one most likely to
surprise somebody adding a method here.
"""

from __future__ import annotations

from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    ApprovalStore,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.audit_repository import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    AuditRepository,
)
from platform.persistence.ports.config_repository import (
    ConfigNode,
    ConfigNodeKind,
    ConfigRepository,
    Organisation,
    OrgDirectory,
)
from platform.persistence.ports.credential_store import (
    REDACTED,
    CredentialMetadata,
    CredentialStore,
    SecretValue,
)
from platform.persistence.ports.episode_store import Episode, EpisodeOutcome, EpisodeStore
from platform.persistence.ports.health import (
    ExtensionStatus,
    HealthState,
    MigrationStatus,
    StoreHealth,
)
from platform.persistence.ports.identity_repository import (
    ApiToken,
    IdentityRepository,
    PrincipalKind,
    RoleBinding,
    TokenDirectory,
    TokenResolution,
    User,
)
from platform.persistence.ports.knowledge_store import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeStore,
)
from platform.persistence.ports.retention import (
    DEFAULT_RETENTION_DAYS,
    DataClass,
    PurgeReport,
    RetentionPolicy,
    RetentionSweeper,
)
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    EvidenceRecord,
    RunStatus,
    RunTrace,
    RunTraceStore,
    ToolCallRecord,
    ToolCallStatus,
    TurnRecord,
)
from platform.persistence.ports.schedule_store import (
    JobClaim,
    JobDispatcher,
    JobOutcome,
    ScheduledJob,
    ScheduleStore,
)
from platform.persistence.ports.session_store import SessionRecord, SessionStore
from platform.persistence.ports.topology_graph import (
    BlastRadius,
    BlastRadiusEntry,
    EdgeKind,
    NodeKind,
    TopologyAvailability,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
    TraversalResult,
)
from platform.persistence.ports.transaction import (
    PersistenceGateway,
    SystemUnitOfWork,
    TenantScope,
    UnitOfWork,
)
from platform.persistence.ports.vector_index import (
    IndexDescriptor,
    SimilarityMatch,
    VectorIndex,
    VectorRecord,
)

__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "REDACTED",
    "ActorKind",
    "AgentRun",
    "ApiToken",
    "ApprovalRequest",
    "ApprovalState",
    "ApprovalStore",
    "AuditEvent",
    "AuditOutcome",
    "AuditRepository",
    "BlastRadius",
    "BlastRadiusEntry",
    "ConfigNode",
    "ConfigNodeKind",
    "ConfigRepository",
    "CredentialMetadata",
    "CredentialStore",
    "DataClass",
    "EdgeKind",
    "Episode",
    "EpisodeOutcome",
    "EpisodeStore",
    "EvidenceRecord",
    "ExtensionStatus",
    "HealthState",
    "IdentityRepository",
    "IndexDescriptor",
    "JobClaim",
    "JobDispatcher",
    "JobOutcome",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeStore",
    "MigrationStatus",
    "NodeKind",
    "OrgDirectory",
    "Organisation",
    "PersistenceGateway",
    "PrincipalKind",
    "PurgeReport",
    "RetentionPolicy",
    "RetentionSweeper",
    "RoleBinding",
    "RollbackPlan",
    "RollbackStep",
    "RunStatus",
    "RunTrace",
    "RunTraceStore",
    "ScheduleStore",
    "ScheduledJob",
    "SecretValue",
    "SessionRecord",
    "SessionStore",
    "SimilarityMatch",
    "StoreHealth",
    "SystemUnitOfWork",
    "TenantScope",
    "TokenDirectory",
    "TokenResolution",
    "ToolCallRecord",
    "ToolCallStatus",
    "TopologyAvailability",
    "TopologyEdge",
    "TopologyGraph",
    "TopologyNode",
    "TraversalResult",
    "TurnRecord",
    "UnitOfWork",
    "User",
    "VectorIndex",
    "VectorRecord",
]
