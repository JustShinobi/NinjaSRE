# Plan — 006 Data Platform

## Summary

Define twelve repository ports with contract suites, implement them over one
PostgreSQL instance using `pgvector` for similarity and Apache AGE for topology,
and enforce with a CI check that nothing outside `platform/persistence/` touches
SQL or Cypher.

## Technical context

| Aspect | Choice |
|---|---|
| Database | PostgreSQL 16+ |
| Vector | `pgvector` with HNSW |
| Graph | Apache AGE (openCypher) |
| ORM / query layer | SQLAlchemy 2.x with async engine |
| Migrations | Alembic, with an advisory lock guarding concurrent start |
| Encryption | SQLAlchemy `TypeDecorator` over AES-GCM; key from operator config |
| Pooling | SQLAlchemy async pool; limits in `config/constants/persistence.py` |
| Test backend | Real Postgres via `testcontainers` for contract suites; in-memory fakes for unit tests, validated by the same suite |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | `RunTraceStore` is what makes evidence durable and replayable |
| II | Traversal depth, result size, pool limits, and retention windows are named constants |
| III | `ApprovalStore` persists approvals and rollback plans as first-class records |
| IV | FR-018, FR-019 — credentials encrypted at rest, never logged; the agent reaches them only via the proxy (feature 007) |
| V | Storage is runtime-agnostic |
| VI | No provider coupling in storage |
| VII | `EpisodeStore` + `VectorIndex` make measured learning possible; retention keeps the corpus intact for ablation |
| VIII | `platform/persistence/` is tier 3; ports are the only export |
| IX | Capability metadata is derived at build time, not stored — no drift between code and database |
| X | Everything stays in the operator's database; no external service |
| XI | **This is the feature.** FR-001 to FR-003 |
| XII | Contract suites written before implementations (SC-005) |
| XIII | Provenance headers on ported models |

**Violations:** none.

## Project structure

```
platform/persistence/
├── ports/
│   ├── config_repository.py     identity_repository.py   audit_repository.py
│   ├── run_trace_store.py       session_store.py         episode_store.py
│   ├── vector_index.py          topology_graph.py        knowledge_store.py
│   ├── approval_store.py        schedule_store.py        credential_store.py
│   └── transaction.py           # composable transaction scope
├── postgres/
│   ├── engine.py                # async engine, pool, health
│   ├── session.py               # unit of work
│   ├── models/                  # SQLAlchemy declarative models
│   ├── repositories/            # one module per port
│   ├── vector/                  # pgvector helpers, index management, re-embedding
│   ├── graph/                   # AGE setup, parameterised traversals
│   └── crypto.py                # encrypted column types
├── migrations/
│   ├── env.py
│   └── versions/
├── fakes/                       # in-memory implementations for unit tests
└── health.py                    # connectivity, extensions, migration status

tests/contract/persistence/      # one suite per port, run against both backends
```

## Graph query catalogue

Fixed, parameterised, and the only queries permitted (FR-016).

| Query | Parameters | Bound |
|---|---|---|
| `upsert_service` | node properties | — |
| `upsert_dependency` | from, to, kind, properties | — |
| `direct_dependencies` | service | `MAX_GRAPH_RESULTS` |
| `direct_dependents` | service | `MAX_GRAPH_RESULTS` |
| `transitive_dependents` | service, depth | `MAX_GRAPH_DEPTH`, `MAX_GRAPH_RESULTS` |
| `blast_radius` | service, depth | `MAX_GRAPH_DEPTH`, `MAX_GRAPH_RESULTS` |
| `shortest_path` | from, to | `MAX_GRAPH_DEPTH` |
| `components_for_episode` | episode | `MAX_GRAPH_RESULTS` |
| `episodes_for_component` | component | `MAX_GRAPH_RESULTS` |

New query shapes are added here deliberately, reviewed, and covered by the
contract suite. No caller composes graph queries.

## Migration discipline

- One logical change per migration, with a tested `downgrade`.
- Index creation uses `CONCURRENTLY`; backfills are batched with a bounded batch
  size (FR-008).
- Applied at start under `pg_advisory_lock` so replicas do not race (FR-007).
- A test applies every migration forward and backward against a database seeded
  with representative data (SC-008).

## Implementation phases

### Phase 1 — Ports and contract suites (test-first)
All twelve port protocols and their contract suites. All red.

### Phase 2 — In-memory fakes
Fakes satisfying every suite, so features 007–017 can be developed and unit-tested
without a database.

### Phase 3 — Engine and schema foundation
Async engine, pool, unit of work, base models with tenant columns, Alembic with
the advisory lock, health checks.

### Phase 4 — Relational repositories
Config, identity, audit, run trace, session, approval, schedule, credential
repositories over the Postgres backend.

### Phase 5 — Vector
`pgvector` setup, HNSW index management, `VectorIndex` implementation,
dimension recording and mismatch failure, background re-embedding.

### Phase 6 — Graph
AGE bootstrap with the degradation path, the fixed traversal catalogue,
`TopologyGraph` implementation, depth and size bounds.

### Phase 7 — Cross-cutting and operations
Encrypted columns, cross-tenant isolation tests, the raw-SQL CI check, retention
policies, backup/restore verification, performance validation for SC-002 and
SC-003.

## Complexity tracking

| Item | Justification |
|---|---|
| Twelve ports rather than one repository | Each has a distinct consumer and lifecycle. One god-repository would be imported by every feature and become the coupling point the layered architecture exists to prevent. |
| Contract suites run against two backends | The in-memory fakes are what let Waves 1–4 develop without a database. Validating them against the same suite is what stops the fakes from diverging into a fiction that passes tests the real store would fail. |
| Fixed graph query catalogue | Constraining callers to nine queries is restrictive, and deliberately so: it prevents LLM-generated Cypher (a correctness and injection risk the upstream implementation carries) and keeps every traversal bounded. |
| `testcontainers` in the contract suite | Slower than SQLite-backed tests, but `pgvector` and AGE behaviour cannot be emulated. The suite runs on a separate CI job so it does not slow the main gate. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Swapnil | `config_service/src/db/` models and repositories | ADAPT — extended for the unified store |
| Swapnil | `config_service/alembic/` | ADAPT |
| Swapnil | `config_service/src/crypto/{encryption,sqlalchemy_types}.py` | ADOPT → `postgres/crypto.py` |
| Swapnil | `sre-agent/memory/store.py` (Neo4j) | REWRITE → `repositories/episode_store.py` over Postgres |
| Swapnil | `sre-agent/memory/neo4j_conn.py` | REWRITE → `postgres/engine.py` |
| Swapnil | `sre-agent/tools/neo4j_semantic_layer.py` | REWRITE → `graph/` traversal catalogue, parameterised |
| Swapnil | `config_service/src/db/scheduled_jobs.py` | ADAPT |
| Tracer | `core/agent_harness/session/persistence/` | ADAPT → `session_store.py` |
| Tracer | `gateway/storage/agent_runs/` | ADAPT → `run_trace_store.py` |
| Tracer | `platform/filestorage/ports.py` port style | REFERENCE — port design conventions |

## Risks

| Risk | Mitigation |
|---|---|
| Apache AGE maturity or Postgres version compatibility | FR-002 degradation path keeps the platform usable without it; the `TopologyGraph` contract suite means a Neo4j adapter is a contained addition if needed |
| Vector search performance at scale | SC-002 validates at 100k episodes with HNSW; index parameters are configurable and recorded so tuning is reproducible |
| Fakes diverge from the real backend | Both run the same contract suite (SC-005); a fake-only pass is not accepted as green |
| Migration downtime on large deployments | Non-blocking index creation and batched backfill (FR-008), verified by SC-008 against seeded data |
| Encryption key loss | Key management is documented in feature 030; the health check reports whether stored credentials are decryptable at start, so misconfiguration surfaces immediately rather than at first use |
