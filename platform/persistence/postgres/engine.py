"""The connection pool, and everything that has to be true before a query runs.

Three jobs, and the third is the one that matters most in an incident.

**Sizing.** Every pool limit is a named constant (Article II). ``max_overflow``
is zero on purpose: an overflow connection is a limit that is not a limit, and a
deployment that quietly opens thirty connections under load is one that hits the
server's own ``max_connections`` at the worst moment instead of its own.

**Statement timeouts.** Set as a server setting on every connection rather than
per query, so a statement nobody thought to bound is still bounded.

**Failing usefully.** SQLAlchemy raises ``TimeoutError`` when the pool is
exhausted, which tells a reader nothing they can act on. ``PoolExhausted``
names the limit, the wait, and the two things that actually cause it (FR-020).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from config.constants.persistence import (
    DATABASE_POOL_MAX_IDLE_SECONDS,
    DATABASE_POOL_MAX_SIZE,
    DATABASE_POOL_TIMEOUT_SECONDS,
    DATABASE_STATEMENT_TIMEOUT_MS,
    DEFAULT_DATABASE_SCHEMA,
    MIGRATION_ADVISORY_LOCK_KEY,
    REQUIRED_POSTGRES_EXTENSIONS,
)
from platform.persistence.errors import PoolExhausted, StoreUnavailable
from platform.persistence.ports.health import ExtensionStatus

#: The driver this package is written against. A URL naming a different one is
#: rewritten rather than rejected: ``postgresql://`` is what an operator's other
#: tools accept, and making them keep two spellings of the same URL is a way to
#: have one of them go stale.
ASYNC_DRIVER = "postgresql+asyncpg"

#: Spellings of a PostgreSQL URL that name a synchronous driver, or none at all.
_SYNC_SCHEMES = frozenset({"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"})


def async_url(url: str) -> str:
    """Return ``url`` pointed at the async driver."""
    scheme, separator, rest = url.partition("://")
    if separator and scheme in _SYNC_SCHEMES:
        return f"{ASYNC_DRIVER}://{rest}"
    return url


def sync_url(url: str) -> str:
    """Return ``url`` pointed at a driver Alembic's synchronous machinery can use."""
    scheme, separator, rest = url.partition("://")
    if separator and scheme == ASYNC_DRIVER:
        return f"postgresql://{rest}"
    return url


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Return an engine with the pool sized from ``config.constants.persistence``."""
    return create_async_engine(
        async_url(url),
        echo=echo,
        pool_size=DATABASE_POOL_MAX_SIZE,
        # Zero on purpose. See the module docstring.
        max_overflow=0,
        pool_timeout=DATABASE_POOL_TIMEOUT_SECONDS,
        pool_recycle=int(DATABASE_POOL_MAX_IDLE_SECONDS),
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "statement_timeout": str(DATABASE_STATEMENT_TIMEOUT_MS),
                "application_name": "ninjasre",
                # Apache AGE resolves its own operators — ``agtype @> agtype``
                # among them — through the search path, so Cypher fails at
                # planning time without ``ag_catalog`` on it. ``public`` stays
                # first: the platform's own tables live there, and a schema
                # whose contents we do not control should not be able to shadow
                # one of them.
                "search_path": f"{DEFAULT_DATABASE_SCHEMA},ag_catalog",
            }
        },
    )


@asynccontextmanager
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Yield a connection, translating pool exhaustion into something actionable."""
    try:
        async with engine.connect() as conn:
            yield conn
    except PoolTimeout as error:
        raise PoolExhausted(
            pool_size=DATABASE_POOL_MAX_SIZE,
            timeout_seconds=DATABASE_POOL_TIMEOUT_SECONDS,
        ) from error


def translate_pool_timeout(error: BaseException) -> BaseException:
    """Return ``PoolExhausted`` if ``error`` is a pool timeout, else ``error``."""
    if isinstance(error, PoolTimeout):
        return PoolExhausted(
            pool_size=DATABASE_POOL_MAX_SIZE,
            timeout_seconds=DATABASE_POOL_TIMEOUT_SECONDS,
        )
    return error


@dataclass(frozen=True, slots=True)
class ServerFacts:
    """What one probe learned about the server it connected to."""

    server_version: int
    extensions: tuple[ExtensionStatus, ...]

    def has(self, extension: str) -> bool:
        """Return whether ``extension`` is installed."""
        return any(status.name == extension and status.available for status in self.extensions)


async def probe_server(conn: AsyncConnection) -> ServerFacts:
    """Return the server's major version and the state of the required extensions."""
    version = await conn.scalar(text("SHOW server_version_num"))
    major = int(str(version)) // 10_000

    rows = await conn.execute(
        text(
            "SELECT name, installed_version FROM pg_available_extensions WHERE name = ANY(:names)"
        ),
        {"names": list(REQUIRED_POSTGRES_EXTENSIONS)},
    )
    installed: dict[str, str | None] = {row.name: row.installed_version for row in rows}

    return ServerFacts(
        server_version=major,
        extensions=tuple(
            ExtensionStatus(
                name=name,
                available=bool(installed.get(name)),
                version=installed.get(name),
            )
            for name in REQUIRED_POSTGRES_EXTENSIONS
        ),
    )


async def ensure_extensions(conn: AsyncConnection) -> tuple[ExtensionStatus, ...]:
    """Install the required extensions where the connected role may, and report what is there.

    Best-effort by design. A managed PostgreSQL commonly refuses ``CREATE
    EXTENSION`` to anything but a superuser and has the extension installed
    already, so a failure here is not conclusive — the probe afterwards is. What
    would be wrong is failing to start over a statement whose result does not
    change the answer.
    """
    for extension in REQUIRED_POSTGRES_EXTENSIONS:
        try:
            await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
        except DBAPIError:
            await conn.rollback()

    return (await probe_server(conn)).extensions


@asynccontextmanager
async def advisory_lock(
    conn: AsyncConnection, key: int = MIGRATION_ADVISORY_LOCK_KEY
) -> AsyncIterator[None]:
    """Hold a session-level advisory lock for the block (FR-007).

    Session-level rather than transaction-level, because Alembic runs each
    migration in its own transaction and a transaction-scoped lock would be
    released between them — which is exactly the window two replicas starting
    together would race in.
    """
    await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
    try:
        yield
    finally:
        await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


async def check_connectivity(engine: AsyncEngine) -> str | None:
    """Return ``None`` if the database answers, or a reason it did not.

    Never raises. It is called by the health check, and a health check that
    throws when the store is down reports nothing about the store being down.
    """
    try:
        async with connection(engine) as conn:
            await conn.execute(text("SELECT 1"))
    except (StoreUnavailable, DBAPIError, OSError) as error:
        return f"The database could not be reached: {type(error).__name__}."
    return None


__all__ = [
    "ASYNC_DRIVER",
    "ServerFacts",
    "advisory_lock",
    "async_url",
    "check_connectivity",
    "connection",
    "create_engine",
    "ensure_extensions",
    "probe_server",
    "sync_url",
    "translate_pool_timeout",
]
