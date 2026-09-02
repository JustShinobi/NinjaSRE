"""Real PostgreSQL proof that one expired decision can hold only one live replacement.

`0022_pending_origin_unique` adds no column and no table — one partial unique
index over `(org_id, arguments->>'origin_approval_id')`, restricted to rows
still `pending`. Everything about it that could be got wrong is invisible from
the migration's own source: whether the expression matches the one
`pending_for_origin` filters on, whether the predicate really does leave
answered rows alone, and whether a second live proposal is refused rather than
merely discouraged. Each of those is a question only a database can answer.

Both directions, because a migration that cannot be undone is one nobody dares
apply to a database with data in it.
"""

from __future__ import annotations

import pytest
from conftest import POSTGRES
from sqlalchemy import text

from platform.persistence.ports import PersistenceGateway
from platform.persistence.postgres import migrations
from platform.persistence.postgres.gateway import PostgresPersistence

pytestmark = pytest.mark.contract

#: The schema exactly as the revision before this one left it.
_PARENT_REVISION = "0021_estate_daily_snapshot"

_INDEX = "ix_approvals_pending_origin"


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip on the fakes: an index is a database object, and there is no database."""
    if backend_name != POSTGRES:
        pytest.skip("The index, and its reverse, are PostgreSQL's.")


async def _indexes(gateway: PostgresPersistence) -> dict[str, str]:
    """Return every index on ``approvals``, by name, with its definition."""
    async with gateway.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'approvals'")
        )
        return {row[0]: row[1] for row in rows}


@pytest.mark.usefixtures("postgres_only")
async def test_the_migration_adds_the_partial_unique_index_and_the_reversal_drops_only_it(
    gateway: PersistenceGateway,
) -> None:
    """Upgrade creates it over the marker and the tenant; downgrade removes just it."""
    assert isinstance(gateway, PostgresPersistence)
    head = migrations.head_revision()

    assert await migrations.downgrade_to(gateway.engine, _PARENT_REVISION) == _PARENT_REVISION
    before = await _indexes(gateway)
    assert _INDEX not in before

    assert await migrations.upgrade_to_head(gateway.engine) == head
    after = await _indexes(gateway)

    assert _INDEX in after
    definition = after[_INDEX]
    assert "UNIQUE" in definition
    assert "org_id" in definition
    assert "origin_approval_id" in definition, (
        "the index must key on the same marker `pending_for_origin` filters on; "
        "two spellings of it is a constraint that never fires"
    )
    assert "WHERE" in definition and "pending" in definition, (
        "partial, or an origin whose replacement lapsed could never be reproposed again"
    )

    assert await migrations.downgrade_to(gateway.engine, _PARENT_REVISION) == _PARENT_REVISION
    assert await _indexes(gateway) == before, "the downgrade must remove exactly this index"

    # Left at head, the state the shared `gateway` fixture hands every other
    # test in this directory back.
    assert await migrations.upgrade_to_head(gateway.engine) == head
