"""The eighteen repository ports, and the unit of work that composes them.

This package is the whole export surface of NinjaSRE's storage layer. Everything
above tier 3 imports from here and from nowhere else in ``persistence/``: the
Postgres implementation, the in-memory fakes, and any future backend are
details, and a caller that named one would be the reason the second could not be
written.

The eighteen, and what each owns:

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
``EstateRepository``         discovered resources, their health, their history
``SignalStore``              the observation history the detectors read
``IncidentStore``            incidents, their subjects, and their timelines
``RemediationLedger``        what each remediation did, and whether it worked
``TransitLedger``            what crossed the boundary, which way, and how it ended
``VerificationLedger``       what has been checked, and what the check found
===========================  ==================================================

They are reached through ``UnitOfWork``, which binds all eighteen to one
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
from platform.persistence.ports.episode_store import (
    Episode,
    EpisodeOutcome,
    EpisodeStore,
    StoredStrategy,
)
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    EstateRepository,
    EstateSummary,
    HealthDerivation,
    HealthSignal,
    HealthTransition,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
    ResourceSource,
    SweepOutcome,
    SweepRecord,
)
from platform.persistence.ports.health import (
    ExtensionStatus,
    HealthState,
    MigrationStatus,
    StoreHealth,
)
from platform.persistence.ports.identity_repository import (
    ApiToken,
    IdentityRepository,
    LocalSignInOpening,
    PrincipalKind,
    RoleBinding,
    TokenDirectory,
    TokenLocation,
    TokenResolution,
    User,
)
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentStore,
    IncidentSubject,
    TimelineEntry,
    TimelineKind,
)
from platform.persistence.ports.knowledge_store import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeStore,
)
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    EffectivenessSummary,
    RecurringProblem,
    RemediationLedger,
    RemediationOutcome,
    RollbackDisposition,
    VerificationState,
    VerificationVerdict,
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
    TraceEventRecord,
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
from platform.persistence.ports.signal_store import (
    Signal,
    SignalKind,
    SignalQuery,
    SignalStore,
)
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
from platform.persistence.ports.transit_ledger import (
    PayloadSample,
    SourceActivity,
    TransitDelivery,
    TransitDirection,
    TransitLedger,
    TransitOutcome,
    TransitQuery,
)
from platform.persistence.ports.vector_index import (
    IndexDescriptor,
    SimilarityMatch,
    VectorIndex,
    VectorRecord,
)
from platform.persistence.ports.verification_ledger import (
    VerificationLedger,
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
)

__all__ = [
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
    "DEFAULT_RETENTION_DAYS",
    "DataClass",
    "EdgeKind",
    "EffectivenessQuery",
    "EffectivenessSummary",
    "Episode",
    "EpisodeOutcome",
    "EpisodeStore",
    "EstateQuery",
    "EstateRepository",
    "EstateSummary",
    "EvidenceRecord",
    "ExtensionStatus",
    "HealthDerivation",
    "HealthSignal",
    "HealthState",
    "HealthTransition",
    "IdentityRepository",
    "Incident",
    "IncidentOrigin",
    "IncidentQuery",
    "IncidentState",
    "IncidentStore",
    "IncidentSubject",
    "IndexDescriptor",
    "JobClaim",
    "JobDispatcher",
    "JobOutcome",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeStore",
    "LocalSignInOpening",
    "MigrationStatus",
    "NodeKind",
    "OrgDirectory",
    "Organisation",
    "PayloadSample",
    "PersistenceGateway",
    "PrincipalKind",
    "PurgeReport",
    "REDACTED",
    "RecurringProblem",
    "ReferenceKind",
    "RemediationLedger",
    "RemediationOutcome",
    "Resource",
    "ResourceHealth",
    "ResourceReference",
    "ResourceSource",
    "RetentionPolicy",
    "RetentionSweeper",
    "RoleBinding",
    "RollbackDisposition",
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
    "Signal",
    "SignalKind",
    "SignalQuery",
    "SignalStore",
    "SimilarityMatch",
    "SourceActivity",
    "StoreHealth",
    "StoredStrategy",
    "SweepOutcome",
    "SweepRecord",
    "SystemUnitOfWork",
    "TenantScope",
    "TimelineEntry",
    "TimelineKind",
    "TokenDirectory",
    "TokenLocation",
    "TokenResolution",
    "ToolCallRecord",
    "ToolCallStatus",
    "TopologyAvailability",
    "TopologyEdge",
    "TopologyGraph",
    "TopologyNode",
    "TraceEventRecord",
    "TransitDelivery",
    "TransitDirection",
    "TransitLedger",
    "TransitOutcome",
    "TransitQuery",
    "TraversalResult",
    "TurnRecord",
    "UnitOfWork",
    "User",
    "VectorIndex",
    "VectorRecord",
    "VerificationLedger",
    "VerificationOutcome",
    "VerificationRecord",
    "VerificationState",
    "VerificationSubject",
    "VerificationVerdict",
]
