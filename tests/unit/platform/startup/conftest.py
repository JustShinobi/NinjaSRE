"""A migrator with no database behind it, and the lock that makes the race real.

``FakeMigrator`` is not a mock. It holds a revision, applies revisions in order,
and serialises everything behind one lock — which is what
``pg_advisory_lock`` does — so the concurrent-replica test is exercising the
same interleaving a rolling deployment produces rather than asserting that a
mock was called once.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from platform.startup.migrations import MigrationOutcome, pending_revisions

REVISIONS: tuple[str, ...] = ("0001", "0002", "0003", "0004")


@dataclass
class SchemaState:
    """One database's revision, shared by every replica pointed at it."""

    applied: str | None = None
    upgrades: int = 0
    applied_by: list[str] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class FakeMigrator:
    """A ``SchemaMigrator`` over shared in-memory state.

    ``fail_at`` makes a named revision raise, which is how the failed-migration
    behaviour is exercised: every revision before it still commits, exactly as
    Alembic's per-revision transactions do.
    """

    state: SchemaState
    replica: str = "replica"
    revisions: tuple[str, ...] = REVISIONS
    head: str = REVISIONS[-1]
    fail_at: str | None = None
    hold_seconds: float = 0.0

    async def expected_revision(self) -> str:
        return self.head

    async def applied_revision(self) -> str | None:
        return self.state.applied

    async def ordered_revisions(self) -> tuple[str, ...]:
        return self.revisions

    async def upgrade_to_head(self) -> MigrationOutcome:
        async with self.state.lock:
            # Re-read under the lock. The loser of a start-up race sees the
            # winner's work here and applies nothing, which is the behaviour a
            # rolling deployment needs.
            before = self.state.applied
            pending = pending_revisions(applied=before, ordered=self.revisions)
            if pending:
                self.state.upgrades += 1
                self.state.applied_by.append(self.replica)
            for revision in pending:
                if self.hold_seconds:
                    await asyncio.sleep(self.hold_seconds)
                if revision == self.fail_at:
                    raise RuntimeError(f"revision {revision} raised")
                self.state.applied = revision
            return MigrationOutcome(
                from_revision=before,
                to_revision=self.state.applied or "",
                applied=pending,
                ran=bool(pending),
            )


@pytest.fixture
def schema() -> SchemaState:
    """Return an empty database, shared by whatever replicas a test makes."""
    return SchemaState()


@pytest.fixture
def migrator(schema: SchemaState) -> FakeMigrator:
    """Return one replica's migrator over an empty database."""
    return FakeMigrator(state=schema)
