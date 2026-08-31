"""Real PostgreSQL proof that the daily estate snapshot table rolls both ways.

`0021_estate_daily_snapshot` adds one table and no backfill — the smallest
class of migration this schema has — but "smallest" is still a real DDL
statement against a real database, and the one thing worth a contract test
here is that upgrading creates exactly the shape the port expects and
downgrading removes exactly that table and nothing else.
"""

from __future__ import annotations

import pytest
from conftest import POSTGRES
from sqlalchemy import text

from platform.persistence.ports import PersistenceGateway
from platform.persistence.postgres import migrations
from platform.persistence.postgres.gateway import PostgresPersistence

pytestmark = pytest.mark.contract

#: The schema exactly as `0019_users_email_optional` left it — the last
#: revision before this feature's table existed.
_PARENT_REVISION = "0019_users_email_optional"


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip on the fakes: there is no in-memory Alembic to roll forward and back."""
    if backend_name != POSTGRES:
        pytest.skip("The migration itself, and its reverse, are PostgreSQL's.")


@pytest.mark.usefixtures("postgres_only")
async def test_the_migration_creates_the_table_and_the_reversal_drops_only_it(
    gateway: PersistenceGateway,
) -> None:
    """Upgrade creates `estate_daily` with its declared columns; downgrade drops only it."""
    assert isinstance(gateway, PostgresPersistence)
    head = migrations.head_revision()

    landed = await migrations.downgrade_to(gateway.engine, _PARENT_REVISION)
    assert landed == _PARENT_REVISION

    async with gateway.engine.connect() as conn:
        before_tables = {
            row[0]
            for row in await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
        }
    assert "estate_daily" not in before_tables

    assert await migrations.upgrade_to_head(gateway.engine) == head

    async with gateway.engine.connect() as conn:
        columns = {
            row[0]: row[1]
            for row in await conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'estate_daily'"
                )
            )
        }
        primary_key = {
            row[0]
            for row in await conn.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = 'estate_daily'::regclass AND i.indisprimary"
                )
            )
        }

    assert columns.keys() == {
        "org_id",
        "snapshot_date",
        "total",
        "counts_by_kind",
        "counts_by_health",
        "captured_at",
    }
    assert columns["snapshot_date"] == "date"
    assert columns["counts_by_kind"] == "jsonb"
    assert columns["counts_by_health"] == "jsonb"
    assert primary_key == {"org_id", "snapshot_date"}, (
        "the natural key must be the primary key: it is what makes a write an "
        "upsert rather than a check-then-insert"
    )

    landed_back = await migrations.downgrade_to(gateway.engine, _PARENT_REVISION)
    assert landed_back == _PARENT_REVISION

    async with gateway.engine.connect() as conn:
        after_tables = {
            row[0]
            for row in await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
        }
    assert "estate_daily" not in after_tables
    assert after_tables == before_tables, "the downgrade must remove exactly this table"

    # Left at head, the same state every other test in this file's directory
    # expects the shared `gateway` fixture to hand back.
    assert await migrations.upgrade_to_head(gateway.engine) == head
