"""Migrations at startup: ordered, skip-tolerant, refused when they do not fit.

The concurrent-replica test at the bottom is the one this file exists for.
Everything else here is a decision about what a revision comparison means; that
one is the failure a rolling deployment actually produces, and it is only
reproducible because the fake serialises on a lock the way the real advisory
lock does.
"""

from __future__ import annotations

import asyncio

import pytest

from platform.startup.errors import MigrationFailed, SchemaIncompatible
from platform.startup.migrations import (
    SchemaMigrator,
    apply_at_startup,
    check_compatibility,
    pending_revisions,
)
from tests.unit.platform.startup.conftest import REVISIONS, FakeMigrator, SchemaState

pytestmark = pytest.mark.unit


def test_the_fake_is_the_port(migrator: FakeMigrator) -> None:
    """A fake that had drifted from the protocol would prove nothing below."""
    assert isinstance(migrator, SchemaMigrator)


# -- what "pending" means -----------------------------------------------------


def test_an_empty_database_has_every_revision_pending() -> None:
    assert pending_revisions(applied=None, ordered=REVISIONS) == REVISIONS


def test_a_schema_at_head_has_none_pending() -> None:
    assert pending_revisions(applied=REVISIONS[-1], ordered=REVISIONS) == ()


def test_skipping_two_versions_leaves_every_revision_in_between() -> None:
    """FR-011: an upgrade that skips releases applies each revision, in order."""
    assert pending_revisions(applied=REVISIONS[0], ordered=REVISIONS) == REVISIONS[1:]


def test_a_revision_this_release_does_not_ship_is_not_a_gap_to_fill() -> None:
    assert pending_revisions(applied="9999", ordered=REVISIONS) == ()


# -- compatibility ------------------------------------------------------------


def test_a_schema_at_the_expected_revision_is_compatible() -> None:
    check_compatibility(applied=REVISIONS[-1], expected=REVISIONS[-1], ordered=REVISIONS)


def test_a_schema_behind_the_code_is_refused_and_says_migrations_have_not_run() -> None:
    with pytest.raises(SchemaIncompatible) as caught:
        check_compatibility(applied=REVISIONS[0], expected=REVISIONS[-1], ordered=REVISIONS)

    assert caught.value.ahead is False
    assert "Migrations have not been applied" in str(caught.value)


def test_a_schema_ahead_of_the_code_is_refused_and_says_roll_forward() -> None:
    """A rollback that put an older release in front of a newer database."""
    with pytest.raises(SchemaIncompatible) as caught:
        check_compatibility(applied="9999", expected=REVISIONS[-1], ordered=REVISIONS)

    assert caught.value.ahead is True
    assert "newer release" in str(caught.value)


def test_an_empty_database_is_named_as_such_rather_than_as_a_revision() -> None:
    with pytest.raises(SchemaIncompatible) as caught:
        check_compatibility(applied=None, expected=REVISIONS[-1], ordered=REVISIONS)

    assert "an empty database" in str(caught.value)


# -- applying -----------------------------------------------------------------


async def test_an_empty_database_is_brought_to_head(migrator: FakeMigrator) -> None:
    outcome = await apply_at_startup(migrator)

    assert outcome.to_revision == REVISIONS[-1]
    assert outcome.applied == REVISIONS
    assert outcome.ran


async def test_a_schema_already_at_head_applies_nothing(schema: SchemaState) -> None:
    schema.applied = REVISIONS[-1]

    outcome = await apply_at_startup(FakeMigrator(state=schema))

    assert not outcome.ran
    assert schema.upgrades == 0
    assert "nothing to apply" in outcome.summary()


async def test_an_upgrade_skipping_two_versions_reports_what_it_applied(
    schema: SchemaState,
) -> None:
    """SC-003: skipping versions applies every revision in order, with no loss."""
    schema.applied = REVISIONS[0]

    outcome = await apply_at_startup(FakeMigrator(state=schema))

    assert outcome.from_revision == REVISIONS[0]
    assert outcome.to_revision == REVISIONS[-1]
    assert outcome.applied == REVISIONS[1:]
    assert outcome.skipped_versions == len(REVISIONS) - 1


async def test_a_database_from_a_newer_release_is_refused_before_anything_is_written(
    schema: SchemaState,
) -> None:
    schema.applied = "9999"

    with pytest.raises(SchemaIncompatible) as caught:
        await apply_at_startup(FakeMigrator(state=schema))

    assert caught.value.ahead is True
    assert schema.upgrades == 0, "a refused start must not have migrated anything"


async def test_migrating_out_of_band_checks_and_refuses_rather_than_writing(
    schema: SchemaState,
) -> None:
    """A Helm release migrates in a job; its replicas must not race the job."""
    schema.applied = REVISIONS[0]

    with pytest.raises(SchemaIncompatible):
        await apply_at_startup(FakeMigrator(state=schema), apply=False)

    assert schema.upgrades == 0


async def test_a_replica_that_migrates_out_of_band_and_finds_head_starts(
    schema: SchemaState,
) -> None:
    schema.applied = REVISIONS[-1]

    outcome = await apply_at_startup(FakeMigrator(state=schema), apply=False)

    assert not outcome.ran


# -- failure (FR-012) ---------------------------------------------------------


async def test_a_failed_migration_names_where_the_schema_actually_stopped(
    schema: SchemaState,
) -> None:
    """FR-012: never an ambiguous state — the message says which revision landed."""
    with pytest.raises(MigrationFailed) as caught:
        await apply_at_startup(FakeMigrator(state=schema, fail_at=REVISIONS[2]))

    assert caught.value.landed == REVISIONS[1], "revisions before the failure committed"
    assert schema.applied == REVISIONS[1]
    assert REVISIONS[1] in str(caught.value)
    assert "resumes from where it stopped" in str(caught.value)


async def test_a_failed_migration_can_be_resumed_by_starting_again(
    schema: SchemaState,
) -> None:
    with pytest.raises(MigrationFailed):
        await apply_at_startup(FakeMigrator(state=schema, fail_at=REVISIONS[2]))

    outcome = await apply_at_startup(FakeMigrator(state=schema))

    assert outcome.to_revision == REVISIONS[-1]
    assert outcome.applied == REVISIONS[2:], "only the revisions that had not landed"


# -- concurrent replicas (T008) -----------------------------------------------


async def test_four_replicas_starting_together_migrate_once_and_all_reach_head(
    schema: SchemaState,
) -> None:
    """FR-007. Without the lock, two replicas interleave and the schema is neither's."""
    replicas = [
        FakeMigrator(state=schema, replica=f"replica-{index}", hold_seconds=0.001)
        for index in range(4)
    ]

    outcomes = await asyncio.gather(*(apply_at_startup(replica) for replica in replicas))

    assert schema.applied == REVISIONS[-1]
    assert schema.upgrades == 1, f"migrated {schema.upgrades} times, by {schema.applied_by}"
    assert len(schema.applied_by) == 1
    assert all(outcome.to_revision == REVISIONS[-1] for outcome in outcomes)
    assert sum(1 for outcome in outcomes if outcome.ran) == 1, "only one replica did work"


async def test_the_replicas_that_lost_the_race_do_not_fail(schema: SchemaState) -> None:
    """The loser waits, finds head, and starts. Failing would break a rolling deploy."""
    replicas = [FakeMigrator(state=schema, replica=f"replica-{index}") for index in range(3)]

    outcomes = await asyncio.gather(
        *(apply_at_startup(replica) for replica in replicas), return_exceptions=True
    )

    assert not [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
