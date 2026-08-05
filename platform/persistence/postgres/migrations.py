"""Applying migrations at startup, under a lock, without racing a second replica.

FR-007 asks for reversible, versioned migrations applied automatically at start
with an advisory lock. The lock is the part worth explaining.

Two replicas starting together both see an out-of-date schema and both run
Alembic. Without a lock they interleave: one creates a table the other is
half-way through creating, and the deployment comes up with a schema neither
migration describes. The lock is *session-level* rather than transaction-level
because Alembic runs each revision in its own transaction — a transaction-scoped
lock would be released between revisions, which is precisely the window the
second replica would start in.

The loser of the race does not fail. It waits, acquires the lock after the
winner has finished, finds the schema already at head, and applies nothing.
That is the behaviour a rolling deployment needs: every replica ends up
correct, and only one of them did any work.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from config.constants.persistence import MIGRATION_ADVISORY_LOCK_KEY, MIGRATION_TABLE_NAME
from platform.persistence.errors import MigrationsPending
from platform.persistence.ports.health import MigrationStatus

#: Where ``env.py``, ``script.py.mako``, and ``versions/`` live.
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def alembic_config() -> Config:
    """Return a config pointed at this package's migration scripts."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", "")
    return config


def head_revision() -> str:
    """Return the revision this release of the code expects."""
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    if len(heads) != 1:
        # Two heads means two branches of migrations were merged without an
        # Alembic merge revision. Applying either would leave the schema
        # describing half the release.
        raise MigrationsPending(applied=None, head=f"{len(heads)} heads: {sorted(heads)}")
    return heads[0]


def status(applied: str | None) -> MigrationStatus:
    """Return the migration status for a database at ``applied``."""
    return MigrationStatus(head_revision=head_revision(), applied_revision=applied)


async def applied_revision(conn: AsyncConnection) -> str | None:
    """Return the revision a database is at, or ``None`` if it has never migrated."""
    return await conn.run_sync(_applied_revision)


def _applied_revision(conn: Connection) -> str | None:
    context = MigrationContext.configure(conn, opts={"version_table": MIGRATION_TABLE_NAME})
    return context.get_current_revision()


async def upgrade_to_head(engine: AsyncEngine) -> str:
    """Bring the schema to head under the advisory lock, and return the revision."""
    return await _run_locked(engine, _upgrade)


async def downgrade_to(engine: AsyncEngine, revision: str) -> str:
    """Roll the schema back to ``revision``, and return where it ended up.

    Exercised by the migration test rather than by the platform: nothing calls
    this at runtime, and an application that downgraded its own schema on start
    would be a way to lose data on a rollback deploy. It exists so that "every
    migration has a tested downgrade" is a claim something checks.
    """

    def _downgrade(conn: Connection) -> None:
        config = alembic_config()
        config.attributes["connection"] = conn
        command.downgrade(config, revision)

    return await _run_locked(engine, _downgrade)


async def _run_locked(engine: AsyncEngine, work: Callable[[Connection], None]) -> str:
    """Hold the advisory lock, run ``work``, and report the resulting revision."""
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_ADVISORY_LOCK_KEY}
        )
        try:
            await conn.run_sync(work)
            await conn.commit()
            return await applied_revision(conn) or ""
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_ADVISORY_LOCK_KEY}
            )


def _upgrade(conn: Connection) -> None:
    config = alembic_config()
    config.attributes["connection"] = conn
    command.upgrade(config, "head")


__all__ = [
    "MIGRATIONS_DIR",
    "alembic_config",
    "applied_revision",
    "downgrade_to",
    "head_revision",
    "status",
    "upgrade_to_head",
]
