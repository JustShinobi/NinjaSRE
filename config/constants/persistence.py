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

DEFAULT_DATABASE_SCHEMA: Final = "public"

#: Extensions the reference deployment requires. Startup verifies these are
#: present rather than failing later inside a query.
REQUIRED_POSTGRES_EXTENSIONS: Final[tuple[str, ...]] = ("vector", "age")

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

#: Server-side statement timeout, in milliseconds.
DATABASE_STATEMENT_TIMEOUT_MS: Final[int] = 30_000

# --- Migrations --------------------------------------------------------------

#: Table recording which reversible migrations have been applied
#: (Article XI, clause 3).
MIGRATION_TABLE_NAME: Final = "ninjasre_schema_migrations"

#: Advisory-lock key held while migrations run, so concurrently starting
#: replicas cannot apply the same migration twice.
MIGRATION_ADVISORY_LOCK_KEY: Final[int] = 8_314_159


__all__ = [
    "DATABASE_POOL_MAX_IDLE_SECONDS",
    "DATABASE_POOL_MAX_SIZE",
    "DATABASE_POOL_MIN_SIZE",
    "DATABASE_POOL_TIMEOUT_SECONDS",
    "DATABASE_STATEMENT_TIMEOUT_MS",
    "DEFAULT_DATABASE_SCHEMA",
    "MIGRATION_ADVISORY_LOCK_KEY",
    "MIGRATION_TABLE_NAME",
    "MINIMUM_POSTGRES_VERSION",
    "NINJASRE_DATABASE_SCHEMA_ENV",
    "NINJASRE_DATABASE_URL_ENV",
    "REQUIRED_POSTGRES_EXTENSIONS",
]
