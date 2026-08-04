# ADR 0004 — Single datastore: PostgreSQL with pgvector and Apache AGE

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article XI, Article X

## Context

NinjaSRE needs four storage shapes:

1. **Relational** — orgs, teams, config nodes, tokens, audit events, approvals,
   run traces, schedules
2. **Vector** — episode embeddings and knowledge-base chunks for semantic recall
3. **Graph** — service topology with dependency traversal and blast-radius queries
4. **Document/JSON** — tool call payloads, evidence blobs, transcripts

The memory design solves this with PostgreSQL (config + agent runs) plus Neo4j (episodic
memory + knowledge graph), retrieving via `neo4j-graphrag`. The pipeline design stores locally
in JSONL with optional Postgres and Redis.

For a self-hosted product, every stateful service is an operational burden the
operator did not ask for: a backup strategy, an upgrade path, a monitoring target,
a security patch cadence, and — in Neo4j's case — a licensing decision, since the
Community Edition lacks clustering, hot backup, and role-based access control.

## Decision

**One PostgreSQL 16+ instance with the `pgvector` and Apache AGE extensions.**

- Relational and JSON: native Postgres
- Vector similarity: `pgvector` with HNSW indexes
- Graph traversal: Apache AGE (openCypher over Postgres)

All access goes through repository ports. No module outside
`platform/persistence/` issues SQL or Cypher.

## Rationale

**Operational economy.** The `standard` deployment profile drops from six
containers to four. One database to back up, restore, upgrade, and monitor.

**Transactional consistency across shapes.** An investigation completing writes a
run trace (relational), an episode with embedding (vector), and component edges
(graph). In a single database that is one transaction. Split across Postgres and
Neo4j it is a distributed write with no rollback story — and the memory design's
implementation indeed logs and swallows memory-write failures, leaving the trace
and the episode inconsistent.

**AGE covers the actual graph workload.** The topology queries in scope are
bounded traversals: direct dependencies, transitive dependents to depth N, blast
radius from a service, and shortest path between two services. AGE's openCypher
support handles these. NinjaSRE does not need Neo4j's algorithm library, and the
prior implementation does not use it either.

**pgvector is sufficient for the recall workload.** Episode counts are in the
thousands to low millions, not billions. HNSW in `pgvector` is well within its
operating envelope at that scale.

**Article X alignment.** Fewer services means fewer network dependencies and a
smaller attack surface for a deployment that must not phone home.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Postgres + Neo4j (the memory design's shape) | Direct reuse of its memory code, but adds a heavyweight stateful service, a licensing decision, cross-store consistency problems, and a second backup strategy |
| Postgres + pgvector, graph optional | Simpler, but makes topology a second-class feature; blast radius is one of the highest-value signals in an investigation and should not be an add-on |
| Ports with the decision deferred | Abstraction without a reference implementation produces ports shaped by nothing; the first concrete backend always defines the contract anyway |

## Consequences

**Positive**

- One backup, one upgrade path, one connection pool, one set of credentials
- Atomic writes across relational, vector, and graph data
- Standard Postgres operational tooling applies to everything
- No commercial licence consideration

**Negative**

- The memory design's Neo4j memory store, `neo4j-graphrag` retrieval, and semantic layer
  must be rewritten rather than adopted
- Apache AGE is younger and less battle-tested than Neo4j; its Postgres version
  compatibility must be tracked
- Cypher syntax coverage in AGE is narrower than Neo4j's

**Mitigations**

- Repository ports mean a Neo4j adapter can be added later without touching
  callers, if AGE proves insufficient
- Graph queries are parameterised traversals written against a documented AGE
  subset — never LLM-generated Cypher, which is both a correctness and an
  injection risk
- A contract test suite runs against the `TopologyGraph` port so an alternative
  backend can be validated
- The Postgres image ships with both extensions pinned and version-tested
