# Feature 006 — Data Platform

- **Wave:** 0 — Foundation
- **Branch:** `feat/006-data-platform`
- **Status:** Draft
- **Depends on:** 001
- **Blocks:** 007, 010, 011, 012, 013, 014, 015, 016, 017
- **ADRs:** [0004](../../docs/adr/0004-single-datastore.md)

## Summary

One PostgreSQL instance holding relational data, vector embeddings, and the
topology graph, behind repository ports that no other module may bypass. This is
the feature that lets an operator run NinjaSRE with a single database to back up,
upgrade, and monitor — and lets an investigation write its trace, its episode, and
its topology edges in one transaction.

## User scenarios

### Primary story

An operator provisions one Postgres instance. Migrations run on start. Everything
the platform persists — config, identity, traces, episodes with embeddings,
service topology — lives there, backed up by one `pg_dump`.

### Acceptance scenarios

1. **Given** a fresh Postgres 16 with `pgvector` and AGE available, **when** the
   platform starts, **then** migrations run to head and the schema is ready.
2. **Given** an investigation completes, **when** its trace, episode, embedding,
   and topology edges are written, **then** all four commit in **one transaction**
   or none do.
3. **Given** 100k episodes, **when** a similarity search runs, **then** the top-k
   nearest neighbours return within the latency target using an HNSW index.
4. **Given** a service topology, **when** a blast-radius query runs for a service,
   **then** transitive dependents to depth N return with a bounded traversal.
5. **Given** a module outside `platform/persistence/`, **when** it attempts raw SQL
   or Cypher, **then** a CI check fails naming the module.
6. **Given** a credential field, **when** it is written, **then** it is encrypted at
   rest and never appears in plaintext in logs or query output.
7. **Given** a schema change, **when** it ships, **then** it is a reversible
   migration with a tested downgrade path.
8. **Given** a multi-tenant deployment, **when** a query runs, **then** it is
   scoped to the requesting org and team, and a test proves cross-tenant reads are
   impossible through the ports.

### Edge cases

- Apache AGE unavailable at start — topology features must degrade to unavailable
  rather than crash the platform.
- `pgvector` dimension mismatch when an embedding model changes.
- A very large evidence payload exceeding a reasonable row size.
- Connection pool exhaustion under concurrent investigations.
- A migration that must backfill a large table without locking it.
- Long-running graph traversal on a pathological topology.

## Requirements

### Functional

**Store and extensions**

- **FR-001** The canonical store MUST be PostgreSQL 16+ with `pgvector` and Apache
  AGE.
- **FR-002** Extension availability MUST be verified at start; unavailable AGE MUST
  degrade topology features to a documented unavailable state, not crash.
- **FR-003** All access MUST go through repository ports. No module outside
  `platform/persistence/` may issue SQL or Cypher. A CI check MUST enforce this.

**Ports**

- **FR-004** The following ports MUST be defined: `ConfigRepository`,
  `IdentityRepository`, `AuditRepository`, `RunTraceStore`, `SessionStore`,
  `EpisodeStore`, `VectorIndex`, `TopologyGraph`, `KnowledgeStore`,
  `ApprovalStore`, `ScheduleStore`, `CredentialStore`.
- **FR-005** Every port MUST have a contract test suite that any implementation
  must pass, enabling alternative backends without touching callers.
- **FR-006** Ports MUST expose transaction scope so a caller can compose several
  writes atomically (FR acceptance 2).

**Schema and migrations**

- **FR-007** Migrations MUST be reversible, versioned, and applied automatically at
  start with an advisory lock so concurrent instances do not race.
- **FR-008** A migration touching a large table MUST be non-blocking (concurrent
  index creation, batched backfill).
- **FR-009** The schema MUST be multi-tenant by construction: every tenant-scoped
  table carries `org_id` and, where applicable, `team_node_id`.
- **FR-010** Cross-tenant access MUST be impossible through the ports; a test MUST
  prove it.

**Vector**

- **FR-011** `VectorIndex` MUST support upsert, delete, and top-k similarity search
  with metadata filtering, scoped by tenant.
- **FR-012** Embedding dimension MUST be recorded per index; a dimension mismatch
  MUST fail loudly at write, not silently degrade search.
- **FR-013** HNSW index parameters MUST be configurable and their values recorded.
- **FR-014** Re-embedding MUST be supported as a background operation without
  downtime for search.

**Graph**

- **FR-015** `TopologyGraph` MUST support: upsert node, upsert edge, direct
  dependencies, transitive dependents to depth N, blast radius from a node,
  shortest path between two nodes.
- **FR-016** All graph queries MUST be parameterised traversals from a fixed set.
  LLM-generated Cypher MUST NOT be executed.
- **FR-017** Traversal depth and result size MUST be bounded by named constants.

**Security and operations**

- **FR-018** Credential and other sensitive columns MUST be encrypted at rest with
  a key from the operator's configuration, using an encrypted SQLAlchemy column
  type.
- **FR-019** Encrypted values MUST never appear in logs, error messages, or query
  echoes.
- **FR-020** Connection pooling MUST be configured with named-constant limits, and
  pool exhaustion MUST produce a clear, actionable error.
- **FR-021** A backup and restore procedure MUST be documented and exercised by a
  test that restores into a clean database and verifies integrity.
- **FR-022** Retention policies MUST be configurable per data class (traces,
  transcripts, episodes, audit) with audit records exempt from automatic deletion.
- **FR-023** Health and readiness checks MUST report store connectivity, extension
  availability, and migration status.

### Key entities

| Entity | Storage shape | Notes |
|---|---|---|
| **Org / TeamNode** | relational | Hierarchy root for all tenant scoping |
| **ConfigNode** | relational + JSONB | Hierarchical config with deep-merge inputs |
| **User / Token / Role** | relational | Identity, with token hashes never plaintext |
| **AuditEvent** | relational, append-only | Immutable; exempt from retention deletion |
| **AgentRun / Turn / ToolCall** | relational + JSONB | The replayable trace |
| **Session** | relational + JSONB | Resumable conversation state |
| **Episode** | relational + vector | Episodic memory with embedding |
| **Strategy** | relational | Synthesised playbook, cached |
| **ServiceNode / DependencyEdge** | AGE graph | Topology |
| **KnowledgeDocument / Chunk** | relational + vector | Runbooks and knowledge base |
| **Approval / RollbackPlan** | relational | Action governance |
| **ScheduledJob / Claim** | relational | Recurring work with distributed claiming |
| **Credential** | relational, encrypted | Never readable by the agent (feature 007) |

## Success criteria

- **SC-001** One transaction commits trace, episode, embedding, and topology edges
  together; an induced failure rolls back all four.
- **SC-002** Top-k search over 100k episodes returns within the configured latency
  target on commodity hardware.
- **SC-003** Blast-radius traversal over a 10k-node topology at depth 3 completes
  within the configured bound.
- **SC-004** The raw-SQL CI check fails on a deliberate violation fixture.
- **SC-005** Every port's contract suite passes against the Postgres
  implementation, and an in-memory fake used for unit tests passes the same suite.
- **SC-006** Cross-tenant read attempts fail through every tenant-scoped port.
- **SC-007** Backup and restore into a clean database preserves referential and
  vector integrity.
- **SC-008** Migrations apply and roll back cleanly on a database seeded with
  representative data.

## Out of scope

- The domain logic that uses each port (features 010–017)
- Credential resolution and the proxy (feature 007)
- Deployment topology and HA (feature 030)

## Clarifications

| Question | Resolution |
|---|---|
| Why not defer the backend choice behind ports alone? | Ports designed without a concrete implementation get shaped by nothing. ADR 0004 picks Postgres as the reference; the ports still permit alternatives, and the contract suite (SC-005) is what makes that real. |
| What if AGE proves insufficient? | The `TopologyGraph` contract suite means a Neo4j adapter can be added without touching callers. FR-002's degradation path means the platform stays usable while that happens. |
| Are JSONB payloads searched? | Traces and evidence are stored as JSONB for replay, with targeted expression indexes on the fields the console filters. They are not a general query surface. |
| How are embeddings versioned? | Each vector row records the embedding model and dimension. FR-014's background re-embed writes a new generation and swaps atomically. |
