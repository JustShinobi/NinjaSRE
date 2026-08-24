"""Real PostgreSQL proof that the identity migration backfills and reverses correctly.

`0017_incident_public_id` is the one migration in this schema that both writes
into every existing row and imports application code to compute what it
writes. Two things about that only a real database, migrated end to end, can
prove: that a database left at the migration's parent revision ends up with
every incident correctly addressed, and that the value it wrote is the value
the code computes for the same row — not merely the same by inspection of two
files that happen to agree today.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import POSTGRES
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.incident_store import is_public_incident_id, public_incident_id
from platform.persistence.postgres import migrations
from platform.persistence.postgres.gateway import PostgresPersistence

pytestmark = pytest.mark.contract

#: The schema exactly as `0016_incident_run_ids_index` left it — the last
#: revision before `public_id` existed, and where every incident this
#: deployment had ever raised actually sat the day this feature shipped.
_PARENT_REVISION = "0016_incident_run_ids_index"

#: Deliberately the shape a real alert-raised incident's primary key has:
#: colons, an `@`, and a fractional-second timestamp — every character the
#: public address exists to stop a screen or a URL from ever carrying again.
_LEGACY_INCIDENT_IDS = (
    "alert:alertmanager:aa11bb22@2026-08-01T00:00:00.100001+00:00",
    "alert:alertmanager:cc33dd44@2026-08-02T00:00:00.200002+00:00",
    "alert:alertmanager:ee55ff66@2026-08-03T00:00:00.300003+00:00",
)


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip on the fakes: there is no in-memory Alembic to roll forward and back."""
    if backend_name != POSTGRES:
        pytest.skip("The migration itself, and its reverse, are PostgreSQL's.")


async def _insert_legacy_incident(conn: AsyncConnection, *, org_id: str, incident_id: str) -> None:
    """Insert one row shaped exactly as `0016_incident_run_ids_index` left the table.

    Before `public_id` existed — the state every incident raised before this
    feature shipped was actually sitting in, and the state the migration's
    backfill has to reach every one of.
    """
    await conn.execute(
        text(
            "INSERT INTO incidents "
            "(org_id, incident_id, correlation_key, title, summary, origin, origin_id, "
            "severity, state, opened_at, closed_at, team_node_id, subjects, run_ids, "
            "actions, close_reason, self_resolved, suppressed_by) "
            "VALUES "
            "(:org_id, :incident_id, :correlation_key, :title, :summary, 'alert', "
            "'alertmanager', 'critical', 'open', :opened_at, NULL, '', "
            "'{\"subjects\": []}'::jsonb, '{}', '{}', '', false, '')"
        ),
        {
            "org_id": org_id,
            "incident_id": incident_id,
            "correlation_key": incident_id.rpartition("@")[0],
            "title": f"Legacy incident {incident_id}",
            "summary": "Recorded before this deployment had a public address.",
            "opened_at": datetime(2026, 8, 1, tzinfo=UTC),
        },
    )


@pytest.mark.usefixtures("postgres_only")
async def test_the_migration_addresses_every_pre_existing_incident_and_reverses_cleanly(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Coverage, uniqueness, an unchanged total, an untouched primary key — then back.

    A database is brought back to the revision before this feature existed,
    seeded with incidents shaped exactly as that revision wrote them, then
    carried forward. What comes out has to cover every row, repeat none of
    them within the organisation, change no count and no primary key. Then
    the reversal is exercised rather than presumed: rolling back has to drop
    exactly the column and index this migration added, with every incident
    still there under the same primary key.
    """
    assert isinstance(gateway, PostgresPersistence)
    head = migrations.head_revision()

    landed = await migrations.downgrade_to(gateway.engine, _PARENT_REVISION)
    assert landed == _PARENT_REVISION

    async with gateway.engine.begin() as conn:
        for incident_id in _LEGACY_INCIDENT_IDS:
            await _insert_legacy_incident(conn, org_id=scope.org_id, incident_id=incident_id)

    async with gateway.engine.connect() as conn:
        before_total = await conn.scalar(text("SELECT count(*) FROM incidents"))

    assert await migrations.upgrade_to_head(gateway.engine) == head

    async with gateway.engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT incident_id, public_id FROM incidents "
                    "WHERE org_id = :org_id ORDER BY incident_id"
                ),
                {"org_id": scope.org_id},
            )
        ).all()
        after_total = await conn.scalar(text("SELECT count(*) FROM incidents"))

    assert after_total == before_total, "the migration must not add or remove a row"

    found_ids = {row.incident_id for row in rows}
    assert found_ids == set(_LEGACY_INCIDENT_IDS), (
        "the migration must never rewrite the primary key it backfills against"
    )

    public_ids = [row.public_id for row in rows]
    assert all(public_ids), "coverage: every row must have gained a public address"
    assert all(is_public_incident_id(value) for value in public_ids), (
        "every backfilled value must have the public address's own grammar"
    )
    assert len(set(public_ids)) == len(public_ids), (
        "uniqueness: no public address may repeat within one organisation"
    )

    landed_back = await migrations.downgrade_to(gateway.engine, _PARENT_REVISION)
    assert landed_back == _PARENT_REVISION

    async with gateway.engine.connect() as conn:
        columns = {
            row[0]
            for row in await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'incidents'"
                )
            )
        }
        assert "public_id" not in columns, "the downgrade must drop the column it added"

        remaining = (
            await conn.execute(
                text("SELECT incident_id FROM incidents WHERE org_id = :org_id"),
                {"org_id": scope.org_id},
            )
        ).all()

    assert {row.incident_id for row in remaining} == set(_LEGACY_INCIDENT_IDS), (
        "the reversal is exercised, not presumed: every incident must still be there"
    )

    # Left at head, the same state every other test in this file's directory
    # expects the shared `gateway` fixture to hand back.
    assert await migrations.upgrade_to_head(gateway.engine) == head


@pytest.mark.usefixtures("postgres_only")
async def test_the_backfilled_value_matches_the_codes_own_derivation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The value the migration writes and the value the code derives, tied together.

    The migration's own `upgrade()` imports `public_incident_id` rather than
    reimplementing its digest, which is what makes this true by construction
    — but a claim true by construction is still worth a test that would fail
    if the construction ever broke. This runs the migration for real and
    recomputes the same function directly against the same primary keys,
    rather than trusting that the import was never quietly duplicated.
    """
    assert isinstance(gateway, PostgresPersistence)
    head = migrations.head_revision()

    landed = await migrations.downgrade_to(gateway.engine, _PARENT_REVISION)
    assert landed == _PARENT_REVISION

    async with gateway.engine.begin() as conn:
        for incident_id in _LEGACY_INCIDENT_IDS:
            await _insert_legacy_incident(conn, org_id=scope.org_id, incident_id=incident_id)

    assert await migrations.upgrade_to_head(gateway.engine) == head

    async with gateway.engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT incident_id, public_id FROM incidents WHERE org_id = :org_id"),
                {"org_id": scope.org_id},
            )
        ).all()

    assert rows, "the fixture must have inserted rows for this to prove anything"
    for row in rows:
        assert row.public_id == public_incident_id(row.incident_id), (
            "the value the migration backfilled and the value the code's own "
            "derivation computes for the same internal key must be identical, "
            "not merely consistent by review"
        )
