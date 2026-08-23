"""The relational schema: every table, with tenancy in its primary key.

FR-009 asks that every tenant-scoped table carry ``org_id``. It is not merely a
column here — it is the first component of each primary key and of each foreign
key. That costs a little index width and buys two things.

A cross-tenant read is not just filtered out, it is *unrepresentable through a
join*: a child row cannot reference a parent in another organisation, because
the composite foreign key would have to name that organisation and the child's
own ``org_id`` is what fills that slot. FR-010 stops depending on every query
remembering a ``WHERE`` clause.

And the natural index for every query the platform makes — always "this
tenant's X" — is the primary key. There is no separate index to forget.

Identifiers are the caller's own strings rather than surrogate integers. A run
id, an episode id, and a credential handle are all meaningful outside the
database, they appear in traces and URLs, and a surrogate key would mean
carrying both.

The one table without an ``org_id`` in its key is ``job_claims``: a claim is the
record that hands work back *across* the tenant boundary, so it carries the
organisation as an ordinary column and the dispatcher reads it without a scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

# The dialect's ARRAY, not the generic one: ``@>`` containment — which is
# how ``by_component`` uses the GIN index on ``episodes.components`` — is
# only defined on the PostgreSQL type. The generic one raises at query
# construction, which is a pleasant place to find out.
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from platform.persistence.postgres.crypto import EncryptedSecret

#: Long enough for a UUID, a URL-safe token id, or a human-chosen handle, and
#: short enough that a composite primary key still fits comfortably in an index
#: page.
ID_LENGTH = 128

#: Names, titles, and other short human text.
NAME_LENGTH = 256


class Base(DeclarativeBase):
    """Declarative base for every NinjaSRE table."""


def _id() -> Mapped[str]:
    """Return a column holding one of the platform's string identifiers."""
    return mapped_column(String(ID_LENGTH), primary_key=True)


def _org() -> Mapped[str]:
    """Return the tenant column, first component of every tenant-scoped key."""
    return mapped_column(String(ID_LENGTH), primary_key=True)


def _timestamp(*, nullable: bool = True) -> Mapped[datetime | None]:
    """Return a timezone-aware timestamp column.

    ``timezone=True`` throughout. A naive timestamp in an incident-response tool
    is a bug waiting for the clocks to change, and PostgreSQL's ``timestamptz``
    costs nothing over ``timestamp``.
    """
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def _json() -> Mapped[dict[str, Any]]:
    """Return a JSONB payload column, defaulting to an empty object."""
    return mapped_column(JSONB, nullable=False, default=dict)


def _tenant_fk(table: str, column: str) -> ForeignKeyConstraint:
    """Return a composite foreign key that cannot cross the tenant boundary."""
    return ForeignKeyConstraint(
        ["org_id", column],
        [f"{table}.org_id", f"{table}.{column}"],
        ondelete="CASCADE",
    )


# --- Tenancy and configuration ------------------------------------------------


class Organisation(Base):
    """A tenant."""

    __tablename__ = "organisations"

    org_id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ConfigNode(Base):
    """One node of an organisation's hierarchy, with the config set at that level."""

    __tablename__ = "config_nodes"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        # Self-referential and composite, so a node cannot be parented into
        # another organisation's tree. No cascade: FR wants the delete refused,
        # and ``ReferencedRecord`` is raised before the database is asked.
        ForeignKeyConstraint(
            ["org_id", "parent_id"], ["config_nodes.org_id", "config_nodes.node_id"]
        ),
        Index("ix_config_nodes_parent", "org_id", "parent_id"),
    )

    org_id: Mapped[str] = _org()
    node_id: Mapped[str] = _id()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    values: Mapped[dict[str, Any]] = _json()
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime | None] = _timestamp()


# --- Identity -----------------------------------------------------------------


class User(Base):
    """A person or service account within one organisation."""

    __tablename__ = "users"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        # Case-insensitive uniqueness is enforced by the repository, which
        # stores and compares a folded copy. A functional unique index would
        # need the same fold and would disagree with Python's on non-ASCII.
        Index("ix_users_email", "org_id", "email_folded", unique=True),
        Index("ix_users_subject", "org_id", "external_subject"),
    )

    org_id: Mapped[str] = _org()
    user_id: Mapped[str] = _id()
    email: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    email_folded: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_subject: Mapped[str | None] = mapped_column(String(NAME_LENGTH), nullable=True)
    # The stored form of a local sign-in passphrase, for a person created with
    # one. Never assigned by `upsert_user` — only `set_local_password` writes
    # this column, so an unrelated update (a display name, a status change)
    # cannot clear it by omission the way a full-row upsert would.
    local_password_hash: Mapped[str | None] = mapped_column(String(NAME_LENGTH), nullable=True)
    created_at: Mapped[datetime | None] = _timestamp()


class ApiToken(Base):
    """A bearer token, recorded by hash and never by value."""

    __tablename__ = "api_tokens"
    __table_args__ = (
        _tenant_fk("users", "user_id"),
        # Global rather than per-tenant: resolution happens before the tenant is
        # known, so the hash has to identify one row in the whole deployment.
        UniqueConstraint("token_hash", name="uq_api_tokens_hash"),
        Index("ix_api_tokens_user", "org_id", "user_id"),
    )

    org_id: Mapped[str] = _org()
    token_id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    team_node_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether this token stands in for the person who holds it — a browser
    # sign-in, the durable credential established from the bootstrap one —
    # rather than for one declared purpose. `False` is the safe default for a
    # row nothing set explicitly: nothing at all, never everything its owner
    # holds.
    unscoped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime | None] = _timestamp()
    expires_at: Mapped[datetime | None] = _timestamp()
    revoked_at: Mapped[datetime | None] = _timestamp()
    last_used_at: Mapped[datetime | None] = _timestamp()


class RoleBinding(Base):
    """A role granted to a principal at a point in the hierarchy."""

    __tablename__ = "role_bindings"
    __table_args__ = (
        _tenant_fk("users", "user_id"),
        Index("ix_role_bindings_user", "org_id", "user_id"),
    )

    org_id: Mapped[str] = _org()
    binding_id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    role: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    granted_at: Mapped[datetime | None] = _timestamp()


# --- Audit --------------------------------------------------------------------


class AuditEvent(Base):
    """One immutable record of something that happened.

    No ``ON DELETE CASCADE`` from ``organisations``, unlike every other table
    here. Removing a tenant must not silently remove the record of what was done
    in it (FR-022), so the reference is declared and restricting.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"]),
        Index("ix_audit_events_time", "org_id", "occurred_at"),
        Index("ix_audit_events_resource", "org_id", "resource_kind", "resource_id"),
        Index("ix_audit_events_actor", "org_id", "actor_id"),
    )

    org_id: Mapped[str] = _org()
    event_id: Mapped[str] = _id()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    action: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, Any]] = _json()


# --- Traces and sessions -------------------------------------------------------


class AgentRun(Base):
    """One investigation."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_agent_runs_started", "org_id", "started_at"),
        Index("ix_agent_runs_status", "org_id", "status"),
        Index("ix_agent_runs_alert", "org_id", "alert_id"),
    )

    org_id: Mapped[str] = _org()
    run_id: Mapped[str] = _id()
    trigger: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = _timestamp()
    finished_at: Mapped[datetime | None] = _timestamp()
    alert_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(NAME_LENGTH), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(NAME_LENGTH), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: One sentence naming the run, apart from the document ``summary`` holds.
    #: ``NOT NULL DEFAULT ''`` — a run from before this column existed reads
    #: as an empty headline, which the read path synthesises one for rather
    #: than treating as a stored fact.
    headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    run_metadata: Mapped[dict[str, Any]] = _json()


class RunTurn(Base):
    """One iteration of the loop."""

    __tablename__ = "run_turns"
    __table_args__ = (
        _tenant_fk("agent_runs", "run_id"),
        Index("ix_run_turns_run", "org_id", "run_id", "index"),
    )

    org_id: Mapped[str] = _org()
    turn_id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = _timestamp()
    finished_at: Mapped[datetime | None] = _timestamp()
    payload: Mapped[dict[str, Any]] = _json()
    usage: Mapped[dict[str, Any]] = _json()


class ToolCall(Base):
    """One capability invocation."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        _tenant_fk("agent_runs", "run_id"),
        Index("ix_tool_calls_run", "org_id", "run_id"),
        Index("ix_tool_calls_name", "org_id", "tool_name"),
    )

    org_id: Mapped[str] = _org()
    call_id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[dict[str, Any]] = _json()
    started_at: Mapped[datetime | None] = _timestamp()
    finished_at: Mapped[datetime | None] = _timestamp()
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    recorded_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Evidence(Base):
    """One observation the system made, citable in a conclusion."""

    __tablename__ = "evidence"
    __table_args__ = (
        _tenant_fk("agent_runs", "run_id"),
        Index("ix_evidence_run", "org_id", "run_id"),
        # The console filters on the source of an observation, and this is the
        # targeted expression index the plan's clarification promises rather
        # than a general query surface over JSONB.
        Index("ix_evidence_source", "org_id", "source"),
    )

    org_id: Mapped[str] = _org()
    evidence_id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    observed_at: Mapped[datetime | None] = _timestamp()
    body: Mapped[dict[str, Any]] = _json()
    cited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TraceEvent(Base):
    """One thing that happened during a run, at its position in the run's log.

    ``sequence`` is per run and assigned inside the run's own transaction, for
    the same reason ``recorded_seq`` is above: a cursor a client presents after
    a dropped connection has to mean the same position on the next read, and two
    events in one concurrent batch routinely share a microsecond.
    """

    __tablename__ = "trace_events"
    __table_args__ = (
        _tenant_fk("agent_runs", "run_id"),
        # The two queries this table serves: catch up a reconnecting client
        # from a cursor, and count what a class of event did across a tenant.
        Index("ix_trace_events_cursor", "org_id", "run_id", "sequence"),
        Index("ix_trace_events_kind", "org_id", "kind"),
    )

    org_id: Mapped[str] = _org()
    event_id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    turn_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    kind: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    occurred_at: Mapped[datetime | None] = _timestamp()
    payload: Mapped[dict[str, Any]] = _json()
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Session(Base):
    """Resumable conversation state, as an opaque payload."""

    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_sessions_status", "org_id", "status", "updated_at"),
    )

    org_id: Mapped[str] = _org()
    session_id: Mapped[str] = _id()
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = _json()
    run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    updated_at: Mapped[datetime | None] = _timestamp()
    expires_at: Mapped[datetime | None] = _timestamp()


# --- Memory and knowledge ------------------------------------------------------


class Episode(Base):
    """One investigation, reduced to what a later one would want to know."""

    __tablename__ = "episodes"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_episodes_signature", "org_id", "signature", "occurred_at"),
        Index("ix_episodes_occurred", "org_id", "occurred_at"),
        Index("ix_episodes_run", "org_id", "run_id"),
        # GIN over the component array: "which incidents involved this service"
        # is a containment test, and a btree cannot answer it.
        Index("ix_episodes_components", "components", postgresql_using="gin"),
    )

    org_id: Mapped[str] = _org()
    episode_id: Mapped[str] = _id()
    title: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    occurred_at: Mapped[datetime | None] = _timestamp()
    components: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    episode_metadata: Mapped[dict[str, Any]] = _json()


class Strategy(Base):
    """One playbook synthesised from a team's episodes.

    The primary key is the synthesis key itself rather than a generated id.
    A strategy *is* its key — there is one playbook per team, issue type, and
    normalised component — so an upsert is a primary-key upsert, and two
    concurrent syntheses cannot produce two rows however they interleave.
    """

    __tablename__ = "strategies"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_strategies_generated", "org_id", "team_node_id", "generated_at"),
    )

    org_id: Mapped[str] = _org()
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(NAME_LENGTH), primary_key=True)
    component_key: Mapped[str] = mapped_column(String(NAME_LENGTH), primary_key=True)
    content: Mapped[dict[str, Any]] = _json()
    generated_at: Mapped[datetime | None] = _timestamp()
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class KnowledgeDocument(Base):
    """One source document, as ingested."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_knowledge_documents_uri", "org_id", "source_uri"),
        Index("ix_knowledge_documents_updated", "org_id", "updated_at"),
    )

    org_id: Mapped[str] = _org()
    document_id: Mapped[str] = _id()
    title: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    checksum: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    updated_at: Mapped[datetime | None] = _timestamp()
    document_metadata: Mapped[dict[str, Any]] = _json()


class KnowledgeChunk(Base):
    """One retrievable passage of a document."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        _tenant_fk("knowledge_documents", "document_id"),
        Index("ix_knowledge_chunks_document", "org_id", "document_id", "ordinal"),
    )

    org_id: Mapped[str] = _org()
    chunk_id: Mapped[str] = _id()
    document_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = _json()


class VectorIndexRow(Base):
    """One declared vector namespace, and which generation searches read.

    The vectors themselves are not here. Each generation gets its own table,
    created with that generation's dimension, because pgvector fixes a column's
    width at creation and a re-embed may change it. This row is the pointer
    ``activate_generation`` moves.
    """

    __tablename__ = "vector_indexes"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )

    org_id: Mapped[str] = _org()
    namespace: Mapped[str] = _id()
    active_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    m: Mapped[int] = mapped_column(Integer, nullable=False)
    ef_construction: Mapped[int] = mapped_column(Integer, nullable=False)
    ef_search: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime | None] = _timestamp()


class VectorGenerationRow(Base):
    """One population of a namespace, and the model that wrote it (FR-012)."""

    __tablename__ = "vector_generations"
    __table_args__ = (_tenant_fk("vector_indexes", "namespace"),)

    org_id: Mapped[str] = _org()
    namespace: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    table_name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    created_at: Mapped[datetime | None] = _timestamp()


# --- Governance ----------------------------------------------------------------


class Approval(Base):
    """One proposed action, awaiting a human."""

    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_approvals_state", "org_id", "state", "requested_at"),
        Index("ix_approvals_run", "org_id", "run_id"),
    )

    org_id: Mapped[str] = _org()
    approval_id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    action: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    side_effect_level: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arguments: Mapped[dict[str, Any]] = _json()
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_at: Mapped[datetime | None] = _timestamp()
    decided_by: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class RollbackPlan(Base):
    """How to undo the action an approval would authorise.

    Keyed by approval rather than by plan id: Article III wants one undo per
    authorised action, and a table that could hold two would need a rule for
    which one runs.
    """

    __tablename__ = "rollback_plans"
    __table_args__ = (
        _tenant_fk("approvals", "approval_id"),
        UniqueConstraint("org_id", "plan_id", name="uq_rollback_plans_plan"),
    )

    org_id: Mapped[str] = _org()
    approval_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime | None] = _timestamp()
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_steps: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    executed_at: Mapped[datetime | None] = _timestamp()


class ScheduledJob(Base):
    """One piece of recurring work."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        # The dispatcher's query: enabled jobs, due now, across every tenant.
        # Organisation last, because it is not a filter there — it is what comes
        # back with the answer.
        Index("ix_scheduled_jobs_due", "enabled", "next_run_at"),
        Index("ix_scheduled_jobs_kind", "org_id", "kind"),
    )

    org_id: Mapped[str] = _org()
    job_id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    schedule: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    next_run_at: Mapped[datetime | None] = _timestamp()
    payload: Mapped[dict[str, Any]] = _json()
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = _timestamp()
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime | None] = _timestamp()


class JobClaim(Base):
    """One worker's lease on one job.

    The one table whose primary key is not tenant-scoped, because a claim is
    what hands work back across the boundary. ``job_id`` is unique so two
    workers cannot hold the same job: the uniqueness is the mutual exclusion,
    rather than a lock somebody has to remember to take.
    """

    __tablename__ = "job_claims"
    __table_args__ = (
        _tenant_fk("scheduled_jobs", "job_id"),
        UniqueConstraint("org_id", "job_id", name="uq_job_claims_job"),
        Index("ix_job_claims_lease", "lease_expires_at"),
    )

    claim_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = _json()


class Credential(Base):
    """One credential, encrypted at rest (FR-018).

    ``secret`` is an ``EncryptedSecret`` column, so what reaches the table is an
    AES-GCM envelope. A dump, a replica, or a psql session without the key sees
    bytes. ``secret_raw`` is the same column read as bytes, which is how
    ``verify_decryptable`` can check every row without decrypting through the
    ORM and turning one bad key into an exception per credential.
    """

    __tablename__ = "credentials"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_credentials_integration", "org_id", "integration"),
    )

    org_id: Mapped[str] = _org()
    handle: Mapped[str] = _id()
    integration: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    secret: Mapped[str] = mapped_column("secret", EncryptedSecret, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime | None] = _timestamp()
    updated_at: Mapped[datetime | None] = _timestamp()
    rotated_at: Mapped[datetime | None] = _timestamp()
    expires_at: Mapped[datetime | None] = _timestamp()


# --- The estate ----------------------------------------------------------------


class EstateResource(Base):
    """One discovered thing the deployment is responsible for.

    ``parent_id`` is an indexed column rather than a self-referencing foreign
    key, and the reason is discovery's ordering: a sweep that enumerates guests
    before nodes would otherwise have to be sorted topologically before a single
    row could be written, and a source that reports a parent it does not itself
    enumerate could never be ingested at all.

    ``(org_id, source, native_id)`` is unique because it is the thing
    ``resource_id`` is derived from. The derivation lives above this layer, so
    the constraint is what makes the property true of the database rather than
    of the code that usually writes to it.
    """

    __tablename__ = "estate_resources"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        # Partial: only one *present* resource per source and native identifier.
        # A provider that reuses an identifier after a deletion gets a new row
        # beside the absent one, which is what keeps the old resource's history
        # from being inherited by whatever took its name.
        Index(
            "uq_estate_resources_native",
            "org_id",
            "source",
            "native_id",
            unique=True,
            postgresql_where=text("absent_since IS NULL"),
        ),
        Index("ix_estate_resources_correlation", "org_id", "kind", "correlation_key"),
        Index("ix_estate_resources_kind", "org_id", "kind"),
        Index("ix_estate_resources_health", "org_id", "health"),
        Index("ix_estate_resources_parent", "org_id", "parent_id"),
        Index("ix_estate_resources_team", "org_id", "team_node_id"),
        Index("ix_estate_resources_source", "org_id", "source"),
    )

    org_id: Mapped[str] = _org()
    resource_id: Mapped[str] = _id()
    kind: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    native_id: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    correlation_key: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    parent_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    team_node_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    attributes: Mapped[dict[str, Any]] = _json()
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    #: Each contributing integration's own view, as a list of objects. A table
    #: would normalise it and buy nothing: nothing joins on a contribution, and
    #: every read of a resource wants all of them.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    health: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The whole derivation — rule, signals, raw provider status, explanation —
    #: so that "why is this degraded" is answered by reading the row.
    derivation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    first_seen_at: Mapped[datetime | None] = _timestamp()
    last_seen_at: Mapped[datetime | None] = _timestamp()
    absent_since: Mapped[datetime | None] = _timestamp()
    maintenance_until: Mapped[datetime | None] = _timestamp()
    maintenance_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class HealthTransitionRow(Base):
    """One recorded change of a resource's state."""

    __tablename__ = "estate_health_transitions"
    __table_args__ = (
        _tenant_fk("estate_resources", "resource_id"),
        Index("ix_estate_transitions_resource", "org_id", "resource_id", "occurred_at"),
        Index("ix_estate_transitions_age", "occurred_at"),
    )

    org_id: Mapped[str] = _org()
    transition_id: Mapped[str] = _id()
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rule: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    signal: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ResourceReferenceRow(Base):
    """A run or an incident that touched a resource.

    The reference kind and identifier are in the primary key, which is what
    makes linking idempotent without a read first: the same run twice is the
    same row.
    """

    __tablename__ = "estate_resource_references"
    __table_args__ = (
        _tenant_fk("estate_resources", "resource_id"),
        Index("ix_estate_references_resource", "org_id", "resource_id", "recorded_at"),
        Index("ix_estate_references_age", "recorded_at"),
    )

    org_id: Mapped[str] = _org()
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    reference_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DiscoverySweep(Base):
    """One discovery sweep, and the cursor the next one resumes from."""

    __tablename__ = "estate_discovery_sweeps"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_estate_sweeps_source", "org_id", "source", "started_at"),
    )

    org_id: Mapped[str] = _org()
    sweep_id: Mapped[str] = _id()
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = _timestamp()
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class SignalRow(Base):
    """One observation about one resource, at one instant, from one source.

    The primary key is the derived signal id rather than a surrogate, which is
    what makes an append idempotent without a read first: a poller that retried
    upserts its own row. The age index is what the retention sweep walks, and
    it is deliberately not tenant-scoped — the sweep runs across the deployment
    and a per-tenant index would be scanned once per organisation.
    """

    __tablename__ = "observation_signals"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_signals_window", "org_id", "name", "resource_id", "observed_at"),
        Index("ix_signals_age", "observed_at"),
    )

    org_id: Mapped[str] = _org()
    signal_id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    state: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    labels: Mapped[dict[str, Any]] = _json()


class TransitDeliveryRow(Base):
    """One crossing of the deployment's boundary, whichever way it went.

    The primary key is the caller's derived delivery id, so a handler that
    retried its own ledger write upserts its own row rather than recording the
    same arrival twice.

    ``ix_transit_recent`` leads with ``(org_id, direction, source, occurred_at)``
    because that is the shape of every read the screen makes: one direction, one
    source, newest first. ``ix_transit_age`` is on the timestamp alone and
    deliberately not tenant-scoped, for the reason ``ix_signals_age`` is not:
    retention sweeps the deployment at once, and leading with ``org_id`` would
    make the sweep one index scan per organisation.
    """

    __tablename__ = "transit_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index("ix_transit_recent", "org_id", "direction", "source", "occurred_at"),
        Index("ix_transit_age", "occurred_at"),
    )

    org_id: Mapped[str] = _org()
    delivery_id: Mapped[str] = _id()
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    matched_rule: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    incident_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    event_type: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detail: Mapped[dict[str, Any]] = _json()


class TransitSampleRow(Base):
    """The last masked payload one source sent.

    Keyed by ``source`` rather than by an identifier of its own, which is what
    makes "one sample per source" a property of the table instead of something
    every writer has to remember. The body stored here has already been through
    the masking policy — there is no column holding a raw payload, so there is
    none to forget to clear.
    """

    __tablename__ = "transit_samples"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )

    org_id: Mapped[str] = _org()
    source: Mapped[str] = mapped_column(String(NAME_LENGTH), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    masking_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VerificationRow(Base):
    """The last check run against one thing, and what it found.

    The primary key is ``(org_id, kind, subject)``, which is the whole design:
    checking the same integration twice upserts its own row, so there is exactly
    one answer to "does this work" by construction rather than because every
    writer remembered to delete the previous one. There is no timestamp in the
    key and no history table beside it — a check is current state, and the port's
    docstring says why keeping every one would be a different feature.

    ``kind`` is in the key because a vendor and a model provider can share a
    name, and one row for both would put a green tick on a model nobody
    exercised.
    """

    __tablename__ = "verifications"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )

    org_id: Mapped[str] = _org()
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject: Mapped[str] = mapped_column(String(NAME_LENGTH), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_by: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    model_id: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")


class IncidentRow(Base):
    """One thing that is wrong, whatever noticed it.

    Subjects, runs, and actions are JSONB and an array rather than child tables.
    They are read only with their incident, never queried across incidents, and
    three joins to render one screen is the cost of a normalisation nothing
    would use. The one thing that *is* queried across incidents —
    ``correlation_key`` for the live incident of a cause — has its own partial
    index, which is what makes correlation a lookup rather than a scan.
    """

    __tablename__ = "incidents"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index(
            "ix_incidents_live_correlation",
            "org_id",
            "correlation_key",
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_incidents_opened", "org_id", "opened_at"),
        Index("ix_incidents_state", "org_id", "state"),
        Index("ix_incidents_team", "org_id", "team_node_id"),
        Index("ix_incidents_age", "closed_at"),
    )

    org_id: Mapped[str] = _org()
    incident_id: Mapped[str] = _id()
    correlation_key: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_id: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = _timestamp()
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    subjects: Mapped[dict[str, Any]] = _json()
    run_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    actions: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    close_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    self_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppressed_by: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")


class IncidentTimelineRow(Base):
    """One thing that happened to an incident, with its cause and its actor."""

    __tablename__ = "incident_timeline"
    __table_args__ = (
        _tenant_fk("incidents", "incident_id"),
        Index("ix_incident_timeline_incident", "org_id", "incident_id", "at"),
    )

    org_id: Mapped[str] = _org()
    entry_id: Mapped[str] = _id()
    incident_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The query an evidence entry ran. Empty for every other kind.
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: What that query returned.
    result: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RemediationOutcomeRow(Base):
    """One remediation, the signals it was meant to move, and what they did.

    The load-bearing index is ``ix_remediation_due``, and it is partial. The
    verification sweep asks "what is owed now" every thirty seconds, and a total
    index would make that a walk over every remediation the deployment has ever
    performed. Restricted to the rows that are still owed it stays a handful
    however much history accumulates — which is the difference between the sweep
    costing nothing and the sweep being the reason the deployment gets slower
    over a year.

    ``ix_remediation_history`` carries the three dimensions effectiveness is
    sliced by, in the order a query narrows: the resource first, because "has
    anything worked on this" is the question a proposal asks.
    """

    __tablename__ = "remediation_outcomes"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        # Partial: the sweep only ever asks about obligations that are still
        # owed, and there are never many of those at once.
        Index(
            "ix_remediation_due",
            "org_id",
            "due_at",
            postgresql_where=text("state <> 'verified'"),
        ),
        Index(
            "ix_remediation_history",
            "org_id",
            "resource_id",
            "capability",
            "condition_key",
            "executed_at",
        ),
        Index("ix_remediation_age", "executed_at"),
    )

    org_id: Mapped[str] = _org()
    action_id: Mapped[str] = _id()
    capability: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    condition_key: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    incident_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    run_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    plan_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settle_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    signal_names: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    before_values: Mapped[dict[str, Any]] = _json()
    after_values: Mapped[dict[str, Any]] = _json()
    verified_at: Mapped[datetime | None] = _timestamp()
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rollback: Mapped[str] = mapped_column(String(32), nullable=False)
    rollback_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    autonomous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    undo: Mapped[dict[str, Any]] = _json()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_holder: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    lease_expires_at: Mapped[datetime | None] = _timestamp()


class RemediationProblemRow(Base):
    """A pattern the ledger's counts raised, closed by a change rather than a fix.

    The partial index mirrors the incident's: a pattern is looked up while it is
    live, once per verified remediation, and a total index would grow with every
    pattern the deployment has ever closed.
    """

    __tablename__ = "remediation_problems"
    __table_args__ = (
        ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        Index(
            "ix_remediation_live_pattern",
            "org_id",
            "pattern_key",
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_remediation_problems_raised", "org_id", "raised_at"),
    )

    org_id: Mapped[str] = _org()
    problem_id: Mapped[str] = _id()
    pattern_key: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    capability: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    incident_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    team_node_id: Mapped[str] = mapped_column(String(ID_LENGTH), nullable=False, default="")
    suppresses_autonomy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed_at: Mapped[datetime | None] = _timestamp()
    close_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    closed_by: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False, default="")


#: Read-only view of the ciphertext, for the decryptability probe. Declared
#: separately rather than as a second mapped attribute because SQLAlchemy would
#: apply the column type to both.
CREDENTIAL_SECRET_COLUMN = "secret"

__all__ = [
    "AgentRun",
    "ApiToken",
    "Approval",
    "AuditEvent",
    "Base",
    "CREDENTIAL_SECRET_COLUMN",
    "ConfigNode",
    "Credential",
    "DiscoverySweep",
    "Episode",
    "EstateResource",
    "Evidence",
    "HealthTransitionRow",
    "ID_LENGTH",
    "IncidentRow",
    "IncidentTimelineRow",
    "JobClaim",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "NAME_LENGTH",
    "Organisation",
    "RemediationOutcomeRow",
    "RemediationProblemRow",
    "ResourceReferenceRow",
    "RoleBinding",
    "RollbackPlan",
    "RunTurn",
    "ScheduledJob",
    "Session",
    "SignalRow",
    "ToolCall",
    "TransitDeliveryRow",
    "TransitSampleRow",
    "User",
    "VectorGenerationRow",
    "VectorIndexRow",
    "VerificationRow",
]
