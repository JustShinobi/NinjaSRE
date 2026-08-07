"""Schema application at startup: locked, ordered, and refused when it does not fit.

Three properties, and each exists because of a specific way a deployment breaks.

**Locked.** Two replicas starting together both see an out-of-date schema and
both migrate. Without a lock they interleave, and the deployment comes up with a
schema neither migration describes. The lock is the storage layer's — a
session-level advisory lock, because Alembic runs each revision in its own
transaction — and this module only insists that the migrator hold it.

**Ordered, with skipping.** An operator who skips two releases applies every
revision in between, in order (FR-011). This is why the migrator is asked for
the whole ordered list rather than only the head: "apply everything after where
you are" is a computation, and reporting *which* revisions ran is what makes an
upgrade auditable afterwards.

**Refused when it does not fit.** A schema behind the code and a schema ahead of
it are different accidents. Behind means migrations have not finished. Ahead
means a rollback put an older release in front of a newer database, and letting
it run would have old code writing rows the new constraints do not describe
(FR-014).

There is one thing this module does not do, and it is the reason it can be
tested without a database: it never touches one. ``SchemaMigrator`` is the port,
``platform.persistence.postgres.migrations.AlembicSchemaMigrator`` is the
adapter, and everything below is a decision about what the answers mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from platform.startup.errors import MigrationFailed, SchemaIncompatible


@runtime_checkable
class SchemaMigrator(Protocol):
    """Applies and reports on this deployment's schema revisions."""

    async def expected_revision(self) -> str:
        """Return the revision this release of the code was written against."""

    async def applied_revision(self) -> str | None:
        """Return the revision the database is at, or ``None`` if it never migrated."""

    async def ordered_revisions(self) -> tuple[str, ...]:
        """Return every revision this release ships, oldest first.

        The order is the migration order, which is what makes "everything after
        where you are" answerable without asking the database.
        """

    async def upgrade_to_head(self) -> MigrationOutcome:
        """Apply every pending revision under the migration lock, and report what *this* did.

        Holds the lock for the whole run rather than per revision: a lock
        released between revisions is exactly the window a second replica would
        start in.

        The outcome is the lock holder's, which is why it is returned from here
        rather than computed by the caller. A replica that waited for the lock
        and then found the schema already at head applied nothing, and a report
        assembled from the revision it read *before* waiting would credit it
        with the winner's work — which is how four replicas each log a
        successful migration that happened once.
        """


@dataclass(frozen=True, slots=True)
class MigrationOutcome:
    """What one startup did to the schema, and what it found."""

    from_revision: str | None
    to_revision: str
    applied: tuple[str, ...] = ()
    ran: bool = False

    @property
    def skipped_versions(self) -> int:
        """Return how many revisions this start had to catch up on (FR-011)."""
        return len(self.applied)

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a startup report serves."""
        return {
            "from_revision": self.from_revision,
            "to_revision": self.to_revision,
            "applied": list(self.applied),
            "ran": self.ran,
        }

    def summary(self) -> str:
        """Return the line a deployment logs after migrating."""
        if not self.ran:
            return f"schema already at {self.to_revision}; nothing to apply"
        start = self.from_revision or "an empty database"
        return (
            f"schema migrated from {start} to {self.to_revision}: "
            f"{len(self.applied)} revision(s) applied"
        )


def pending_revisions(
    *,
    applied: str | None,
    ordered: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the revisions after ``applied``, in migration order.

    An empty database gets every revision. A revision the ordered list does not
    contain returns nothing, because it is not a gap — it is a database from a
    newer release, which ``check_compatibility`` refuses rather than fills in.
    """
    if applied is None:
        return ordered
    if applied not in ordered:
        return ()
    return ordered[ordered.index(applied) + 1 :]


def check_compatibility(
    *,
    applied: str | None,
    expected: str,
    ordered: tuple[str, ...],
) -> None:
    """Raise ``SchemaIncompatible`` unless the schema is one this release can run on (FR-014).

    "Can run on" means exactly at the expected revision. Being behind is not
    tolerated even by one revision: the code was written against the columns the
    pending revision adds, and a deployment that served traffic anyway would
    fail on the first query that used one.
    """
    if applied == expected:
        return
    ahead = applied is not None and applied not in ordered
    raise SchemaIncompatible(applied=applied, expected=expected, ahead=ahead)


async def apply_at_startup(
    migrator: SchemaMigrator,
    *,
    apply: bool = True,
) -> MigrationOutcome:
    """Bring the schema to the revision this release expects, and report what happened.

    ``apply=False`` is the deployment that migrates out of band — a Helm job, a
    DBA, a maintenance window. It checks and refuses rather than writing, which
    is the behaviour a replica needs when something else owns the schema.

    Raises:
        SchemaIncompatible: the schema is not one this release can run against.
        MigrationFailed: a revision raised; the message names where the schema
            actually ended up, so the state is recoverable rather than unknown.
    """
    expected = await migrator.expected_revision()
    before = await migrator.applied_revision()

    if before == expected:
        return MigrationOutcome(from_revision=before, to_revision=expected, ran=False)

    ordered = await migrator.ordered_revisions()

    if not apply:
        check_compatibility(applied=before, expected=expected, ordered=ordered)
        return MigrationOutcome(from_revision=before, to_revision=expected, ran=False)

    # Refuse a database from a newer release before writing anything to it.
    # Running migrations forward from an unknown revision is how a rollback
    # turns into a schema nobody can describe.
    if before is not None and before not in ordered:
        raise SchemaIncompatible(applied=before, expected=expected, ahead=True)

    try:
        outcome = await migrator.upgrade_to_head()
    except Exception as error:
        # FR-012: never an ambiguous state. Each revision commits on its own, so
        # the schema is at the last one that succeeded — this reads it back and
        # says so, which is the difference between "recoverable" and "unknown".
        landed = await _revision_after_failure(migrator)
        raise MigrationFailed(
            attempted=expected, landed=landed, reason=str(error) or type(error).__name__
        ) from error

    check_compatibility(applied=outcome.to_revision, expected=expected, ordered=ordered)
    return outcome


async def _revision_after_failure(migrator: SchemaMigrator) -> str | None:
    """Return where the schema ended up, or ``None`` if even that cannot be read."""
    try:
        return await migrator.applied_revision()
    except Exception:
        # A migrator that cannot report its own revision after a failure is a
        # database that is not answering at all. Reporting the original failure
        # matters more than this one, and ``MigrationFailed`` says the landing
        # revision is unknown rather than inventing one.
        return None


__all__ = [
    "MigrationOutcome",
    "SchemaMigrator",
    "apply_at_startup",
    "check_compatibility",
    "pending_revisions",
]
