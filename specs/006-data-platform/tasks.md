# Tasks — 006 Data Platform

## Phase 1 — Ports and contract suites (test-first)

- **T001** `ports/transaction.py`: composable transaction scope (FR-006).
- **T002** [P] `ports/config_repository.py` + contract suite.
- **T003** [P] `ports/identity_repository.py` + contract suite.
- **T004** [P] `ports/audit_repository.py` + contract suite (append-only).
- **T005** [P] `ports/run_trace_store.py` + contract suite.
- **T006** [P] `ports/session_store.py` + contract suite.
- **T007** [P] `ports/episode_store.py` + contract suite.
- **T008** [P] `ports/vector_index.py` + contract suite.
- **T009** [P] `ports/topology_graph.py` + contract suite (the nine fixed queries).
- **T010** [P] `ports/knowledge_store.py` + contract suite.
- **T011** [P] `ports/approval_store.py` + contract suite.
- **T012** [P] `ports/schedule_store.py` + contract suite.
- **T013** [P] `ports/credential_store.py` + contract suite.
- **T014** Cross-tenant isolation cases in every tenant-scoped suite (FR-010).
- **T015** Atomic multi-port write case: trace + episode + embedding + edges
  (SC-001).

## Phase 2 — In-memory fakes

- **T016** `fakes/` implementations for all twelve ports.
- **T017** Run every contract suite against the fakes; all green (part of SC-005).
- **T018** Export a `FakePersistence` fixture for downstream feature development.

## Phase 3 — Engine and schema foundation

- **T019** `postgres/engine.py`: async engine, pool sized from
  `config/constants/persistence.py`, actionable pool-exhaustion error (FR-020).
- **T020** `postgres/session.py`: unit of work implementing the transaction port.
- **T021** Base declarative model with `org_id` / `team_node_id` and timestamp
  mixins (FR-009).
- **T022** Alembic setup with an advisory lock around start-time migration
  (FR-007).
- **T023** Extension bootstrap: `CREATE EXTENSION` for `vector` and `age`;
  availability probe (FR-002).
- **T024** AGE-unavailable degradation path with a documented unavailable state.
- **T025** `health.py`: connectivity, extension availability, migration status
  (FR-023).
- **T026** `testcontainers` fixture providing Postgres with both extensions.

## Phase 4 — Relational repositories

- **T027** Models and migration for orgs, team nodes, config nodes.
- **T028** [P] `repositories/config_repository.py`.
- **T029** Models and migration for users, tokens, roles, SSO bindings.
- **T030** [P] `repositories/identity_repository.py` (token hashes only, never
  plaintext).
- **T031** Models and migration for audit events, append-only with a delete guard.
- **T032** [P] `repositories/audit_repository.py`.
- **T033** Models and migration for runs, turns, tool calls, evidence (JSONB with
  targeted expression indexes).
- **T034** [P] `repositories/run_trace_store.py`.
- **T035** [P] `repositories/session_store.py`.
- **T036** Models and migration for approvals and rollback plans.
- **T037** [P] `repositories/approval_store.py`.
- **T038** Models and migration for scheduled jobs and claims.
- **T039** [P] `repositories/schedule_store.py`.
- **T040** Models and migration for credentials (encrypted columns).
- **T041** [P] `repositories/credential_store.py`.

## Phase 5 — Vector

- **T042** `vector/schema.py`: embedding columns with recorded model and dimension
  (FR-012).
- **T043** `vector/index.py`: HNSW creation with configurable, recorded parameters
  (FR-013).
- **T044** `repositories/vector_index.py`: upsert, delete, top-k with metadata
  filtering, tenant-scoped (FR-011).
- **T045** Dimension-mismatch write failure test — loud, not silent.
- **T046** `vector/reembed.py`: background re-embedding writing a new generation
  and swapping atomically, with search available throughout (FR-014).
- **T047** Models and migration for episodes and knowledge chunks with vectors.
- **T048** [P] `repositories/episode_store.py`.
- **T049** [P] `repositories/knowledge_store.py`.
- **T050** Seed 100k synthetic episodes; validate top-k latency (SC-002).

## Phase 6 — Graph

- **T051** `graph/bootstrap.py`: AGE graph creation and label setup.
- **T052** `graph/queries.py`: the nine parameterised traversals, each bounded by
  `MAX_GRAPH_DEPTH` and `MAX_GRAPH_RESULTS` (FR-015, FR-017).
- **T053** Guard: no query string is constructed from caller-supplied text
  (FR-016); test with an injection-shaped input.
- **T054** `repositories/topology_graph.py`.
- **T055** Seed a 10k-node topology; validate depth-3 blast radius (SC-003).
- **T056** Contract suite green against the Postgres implementation for all twelve
  ports (SC-005).

## Phase 7 — Cross-cutting and operations

- **T057** `postgres/crypto.py`: encrypted `TypeDecorator`, key from operator
  config (FR-018).
- **T058** Test: encrypted values never appear in logs, errors, or query echoes
  (FR-019).
- **T059** Write `tools/check_raw_sql.py`: fail on SQL or Cypher outside
  `platform/persistence/`; violation fixture (SC-004).
- **T060** Wire it into `make verify`.
- **T061** Confirm cross-tenant isolation across all ports (SC-006).
- **T062** Retention policies per data class; audit exempt from deletion (FR-022).
- **T063** Backup and restore procedure documented; test restoring into a clean
  database and verifying referential and vector integrity (SC-007, FR-021).
- **T064** Migration up/down test against seeded representative data (SC-008).
- **T065** Confirm SC-001 atomic multi-port transaction against Postgres.
- **T066** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Four-way atomic write commits or rolls back together (SC-001)
- [ ] 100k-episode top-k within latency target (SC-002)
- [ ] 10k-node depth-3 blast radius within bound (SC-003)
- [ ] Raw-SQL check fails on the violation fixture (SC-004)
- [ ] All twelve contract suites green on Postgres and on fakes (SC-005)
- [ ] Cross-tenant reads impossible through every port (SC-006)
- [ ] Backup/restore preserves integrity (SC-007)
- [ ] Migrations reversible against seeded data (SC-008)
- [ ] `make verify` green
