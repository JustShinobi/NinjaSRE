"""The single datastore: connection, pooling, and migration names.

One PostgreSQL instance with ``pgvector`` and Apache AGE holds relational
config, vector memory, and the topology graph (Constitution Article XI). There
is no second stateful service to name here, and adding one is an ADR, not a
constant.

The URL's *name* lives here; its *value* is resolved through the credential
vault like any other secret (Article IV).
"""

from __future__ import annotations

from typing import Final

# --- Connection --------------------------------------------------------------

NINJASRE_DATABASE_URL_ENV: Final = "NINJASRE_DATABASE_URL"
NINJASRE_DATABASE_SCHEMA_ENV: Final = "NINJASRE_DATABASE_SCHEMA"

#: Key that encrypts credential columns at rest (FR-018). The *name* is here;
#: the key itself is resolved like any other secret and never written down.
NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: Final = "NINJASRE_DATABASE_ENCRYPTION_KEY"

#: AES-256. Shorter keys are refused rather than stretched: a deployment that
#: configured 16 bytes should be told, not quietly given less than it asked for.
DATABASE_ENCRYPTION_KEY_BYTES: Final[int] = 32

#: Points the persistence contract suite at a live PostgreSQL. Unset means the
#: suite runs against the in-memory fakes alone and says so, rather than
#: reporting a pass it did not earn.
NINJASRE_TEST_DATABASE_URL_ENV: Final = "NINJASRE_TEST_DATABASE_URL"

DEFAULT_DATABASE_SCHEMA: Final = "public"

#: Extensions the reference deployment requires. Startup verifies these are
#: present rather than failing later inside a query.
REQUIRED_POSTGRES_EXTENSIONS: Final[tuple[str, ...]] = ("vector", "age")

#: The subset whose absence degrades the platform instead of stopping it
#: (FR-002). Without AGE there is no topology, and an investigation without a
#: blast radius is a worse investigation rather than an impossible one. Without
#: ``vector`` there is no episodic recall and no knowledge retrieval, which is
#: most of what the platform is for.
DEGRADABLE_POSTGRES_EXTENSIONS: Final[frozenset[str]] = frozenset({"age"})

#: Minimum server version. pgvector's HNSW indexes and AGE both assume it.
MINIMUM_POSTGRES_VERSION: Final[int] = 16

# --- Pooling -----------------------------------------------------------------

DATABASE_POOL_MIN_SIZE: Final[int] = 1
DATABASE_POOL_MAX_SIZE: Final[int] = 10

#: Seconds a caller waits for a free connection before failing. Short on
#: purpose: a saturated pool should surface as an error, not as a hung
#: investigation.
DATABASE_POOL_TIMEOUT_SECONDS: Final[float] = 30.0

#: Seconds a connection may sit idle before the pool recycles it.
DATABASE_POOL_MAX_IDLE_SECONDS: Final[float] = 300.0

#: How long an identifier column is, and therefore the longest identifier
#: anything may derive.
#:
#: Stated here rather than only in the table definition because the code that
#: *mints* an identifier is what has to respect it, and that code sits nowhere
#: near the schema. An id composed past this width fails on write with a
#: database error that reads like an outage, and the in-memory store used by
#: almost every test has no widths at all — so the arithmetic has to be
#: checkable without a real PostgreSQL.
MAX_IDENTIFIER_CHARS: Final[int] = 128

#: Server-side statement timeout, in milliseconds.
DATABASE_STATEMENT_TIMEOUT_MS: Final[int] = 30_000

# --- Migrations --------------------------------------------------------------

#: Table recording which reversible migrations have been applied
#: (Article XI, clause 3).
MIGRATION_TABLE_NAME: Final = "ninjasre_schema_migrations"

#: Advisory-lock key held while migrations run, so concurrently starting
#: replicas cannot apply the same migration twice.
MIGRATION_ADVISORY_LOCK_KEY: Final[int] = 8_314_159

#: Advisory-lock key held while a caller decides whether it is the one that
#: opens this deployment's local sign-in — the same kind of exclusion as
#: ``MIGRATION_ADVISORY_LOCK_KEY``, with a key of its own so the two never
#: contend with each other.
LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY: Final[int] = 8_314_160

#: Rows rewritten per statement when a migration backfills an existing table
#: (FR-008). Small enough that each batch is a short transaction, so a backfill
#: on a live deployment never holds a lock long enough to stall an
#: investigation writing its trace.
MIGRATION_BACKFILL_BATCH_SIZE: Final[int] = 5_000

# --- Query bounds ------------------------------------------------------------

#: Rows any single listing may return. A caller that wants more asks again with
#: a cursor; a caller that wanted everything at once wanted a report, not a
#: query.
MAX_QUERY_PAGE_SIZE: Final[int] = 200

#: Ceiling on one JSONB payload — a trace turn, an evidence body, a session
#: snapshot. PostgreSQL would TOAST far more than this without complaint, which
#: is the problem: an unbounded evidence blob is discovered at restore time.
MAX_JSONB_PAYLOAD_BYTES: Final[int] = 1_048_576

# --- Vector ------------------------------------------------------------------

DEFAULT_VECTOR_TOP_K: Final[int] = 10

#: Neighbours one search may return. Past this the result stops being "similar
#: incidents" and becomes a corpus dump the context budget cannot hold.
MAX_VECTOR_TOP_K: Final[int] = 100

#: pgvector refuses an HNSW index above 2000 dimensions. Recording the limit
#: here means a model that exceeds it fails at index creation with a name to
#: blame, rather than at the first search with a planner error.
MAX_INDEXABLE_EMBEDDING_DIMENSION: Final[int] = 2_000

#: HNSW build parameters (FR-013). Recorded per index so a tuning change is
#: visible in the index descriptor rather than inferred from search latency.
HNSW_M: Final[int] = 16
HNSW_EF_CONSTRUCTION: Final[int] = 64

#: Search-time candidate list. Must be at least the requested ``k`` or the
#: index returns fewer neighbours than asked for.
HNSW_EF_SEARCH: Final[int] = 40

#: Budget for a top-k search over the SC-002 corpus, on commodity hardware.
VECTOR_SEARCH_LATENCY_BUDGET_MS: Final[int] = 200

#: The two vector index namespaces the platform declares for itself. Each holds
#: one kind of thing embedded by one model, because an index mixing episode
#: summaries with runbook paragraphs returns neighbours from whichever corpus
#: happens to be denser.
EPISODE_VECTOR_NAMESPACE: Final = "episodes"
KNOWLEDGE_VECTOR_NAMESPACE: Final = "knowledge"

# --- Graph -------------------------------------------------------------------

#: Name of the Apache AGE graph holding service topology. One graph, because a
#: second one would need a rule for which edges live where.
TOPOLOGY_GRAPH_NAME: Final = "ninjasre_topology"

#: Hops any traversal may take (FR-017). Beyond five, blast radius in a
#: service graph of any size returns most of the estate, and an answer that
#: names everything answers nothing. The bound is semantic rather than a budget:
#: a traversal is an indexed walk over the subgraph it reaches, so its cost
#: follows the size of the answer rather than the size of the estate, and depth
#: five over forty thousand nodes is single-digit milliseconds. What actually
#: binds first at this depth is ``MAX_GRAPH_RESULTS``.
MAX_GRAPH_DEPTH: Final[int] = 5

#: Depth used when a caller does not name one. Deep enough to cross a
#: service's dependencies and their backing stores.
DEFAULT_GRAPH_DEPTH: Final[int] = 3

#: Nodes one traversal may return (FR-017), bounding a pathological topology
#: before it bounds the process.
MAX_GRAPH_RESULTS: Final[int] = 500

#: Budget for a depth-3 blast radius over the SC-003 topology.
GRAPH_TRAVERSAL_LATENCY_BUDGET_MS: Final[int] = 500

# --- Scheduling --------------------------------------------------------------

#: How long a claimed job stays claimed without a heartbeat. A worker that dies
#: mid-job blocks the schedule for at most this long.
JOB_CLAIM_LEASE_SECONDS: Final[float] = 300.0

#: Jobs one worker may claim in a single pass, so a backlog is shared out
#: rather than swallowed by whichever worker polled first.
MAX_JOB_CLAIM_BATCH: Final[int] = 50

# --- Retention ---------------------------------------------------------------

#: Days each data class is kept before a retention pass may delete it
#: (FR-022). Episodes outlive traces by a wide margin on purpose: the trace is
#: the evidence for one investigation, the episode is the corpus every ablation
#: measures learning against, and deleting the corpus deletes the ability to
#: prove the system improved.
RETENTION_DAYS_RUN_TRACES: Final[int] = 90
RETENTION_DAYS_SESSIONS: Final[int] = 30
RETENTION_DAYS_EPISODES: Final[int] = 730
RETENTION_DAYS_KNOWLEDGE: Final[int] = 730

#: Data classes no retention pass may delete, whatever the operator configures
#: (FR-022). An audit trail with a deletion path is not an audit trail.
RETENTION_EXEMPT_DATA_CLASSES: Final[frozenset[str]] = frozenset({"audit"})


__all__ = [
    "DATABASE_ENCRYPTION_KEY_BYTES",
    "DATABASE_POOL_MAX_IDLE_SECONDS",
    "MAX_IDENTIFIER_CHARS",
    "DATABASE_POOL_MAX_SIZE",
    "DATABASE_POOL_MIN_SIZE",
    "DATABASE_POOL_TIMEOUT_SECONDS",
    "DATABASE_STATEMENT_TIMEOUT_MS",
    "DEFAULT_DATABASE_SCHEMA",
    "DEFAULT_GRAPH_DEPTH",
    "DEFAULT_VECTOR_TOP_K",
    "DEGRADABLE_POSTGRES_EXTENSIONS",
    "EPISODE_VECTOR_NAMESPACE",
    "GRAPH_TRAVERSAL_LATENCY_BUDGET_MS",
    "HNSW_EF_CONSTRUCTION",
    "HNSW_EF_SEARCH",
    "HNSW_M",
    "JOB_CLAIM_LEASE_SECONDS",
    "KNOWLEDGE_VECTOR_NAMESPACE",
    "LOCAL_SIGN_IN_OPEN_ADVISORY_LOCK_KEY",
    "MAX_GRAPH_DEPTH",
    "MAX_GRAPH_RESULTS",
    "MAX_INDEXABLE_EMBEDDING_DIMENSION",
    "MAX_JOB_CLAIM_BATCH",
    "MAX_JSONB_PAYLOAD_BYTES",
    "MAX_QUERY_PAGE_SIZE",
    "MAX_VECTOR_TOP_K",
    "MIGRATION_ADVISORY_LOCK_KEY",
    "MIGRATION_BACKFILL_BATCH_SIZE",
    "MIGRATION_TABLE_NAME",
    "MINIMUM_POSTGRES_VERSION",
    "NINJASRE_DATABASE_ENCRYPTION_KEY_ENV",
    "NINJASRE_DATABASE_SCHEMA_ENV",
    "NINJASRE_DATABASE_URL_ENV",
    "NINJASRE_TEST_DATABASE_URL_ENV",
    "REQUIRED_POSTGRES_EXTENSIONS",
    "RETENTION_DAYS_EPISODES",
    "RETENTION_DAYS_KNOWLEDGE",
    "RETENTION_DAYS_RUN_TRACES",
    "RETENTION_DAYS_SESSIONS",
    "RETENTION_EXEMPT_DATA_CLASSES",
    "TOPOLOGY_GRAPH_NAME",
    "VECTOR_SEARCH_LATENCY_BUDGET_MS",
]
