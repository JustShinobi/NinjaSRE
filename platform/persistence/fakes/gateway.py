"""An in-memory ``PersistenceGateway`` with real transactions.

The transactions are the point. A fake that applied writes immediately would
pass every single-repository test and then let SC-001 — trace, episode,
embedding, and topology edges committing together or not at all — pass without
proving anything, because there would be nothing to roll back.

So ``begin`` deep-copies the store, hands the copy to a unit of work, and swaps
it in only if the block exits cleanly. A unit that raises, or that marked itself
rollback-only, leaves the committed state exactly as it was — across all thirteen
repositories, because they were all writing into the same copy.

Two consequences worth knowing before you use this:

**Units of work serialise.** One lock, held for the length of the block. That is
stronger than any isolation level a real database offers, and it is the right
trade for a fake: tests get determinism, and nothing depends on the fake to
reproduce a race that only Postgres can really have.

**Units of work do not nest.** Opening one inside another deadlocks on that
lock. Nesting was never meaningful here anyway — the inner block would be
composing into a transaction it did not open — and failing loudly beats
silently sharing the outer one.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from platform.persistence.errors import RecordNotFound
from platform.persistence.fakes.approval_store import FakeApprovalStore
from platform.persistence.fakes.audit_repository import FakeAuditRepository
from platform.persistence.fakes.config_repository import FakeConfigRepository, FakeOrgDirectory
from platform.persistence.fakes.credential_store import FakeCredentialStore
from platform.persistence.fakes.episode_store import FakeEpisodeStore
from platform.persistence.fakes.estate_repository import FakeEstateRepository
from platform.persistence.fakes.identity_repository import (
    FakeIdentityRepository,
    FakeTokenDirectory,
)
from platform.persistence.fakes.knowledge_store import FakeKnowledgeStore
from platform.persistence.fakes.retention import FakeRetentionSweeper
from platform.persistence.fakes.run_trace_store import FakeRunTraceStore
from platform.persistence.fakes.schedule_store import FakeJobDispatcher, FakeScheduleStore
from platform.persistence.fakes.session_store import FakeSessionStore
from platform.persistence.fakes.signal_store import FakeSignalStore
from platform.persistence.fakes.state import State, TenantState
from platform.persistence.fakes.topology_graph import FakeTopologyGraph
from platform.persistence.fakes.vector_index import FakeVectorIndex
from platform.persistence.health import summarise
from platform.persistence.ports.config_repository import OrgDirectory
from platform.persistence.ports.health import ExtensionStatus, MigrationStatus, StoreHealth
from platform.persistence.ports.identity_repository import TokenDirectory
from platform.persistence.ports.retention import RetentionSweeper
from platform.persistence.ports.schedule_store import JobDispatcher
from platform.persistence.ports.transaction import (
    PersistenceGateway,
    SystemUnitOfWork,
    TenantScope,
    UnitOfWork,
)

#: The revision an in-memory store reports. It has no migrations, so it is
#: always at head — and saying so keeps ``summarise`` on the same code path it
#: takes against a real database rather than a special case for the fake.
FAKE_HEAD_REVISION = "in-memory"


@dataclass(slots=True)
class FakeUnitOfWork:
    """Fourteen repositories over one tenant's slice of one snapshot."""

    scope: TenantScope
    state: State
    _rollback_only: bool = field(default=False, repr=False)

    @property
    def config(self) -> FakeConfigRepository:
        """Return the hierarchy and configuration repository."""
        return FakeConfigRepository(self.scope.org_id, self._tenant)

    @property
    def identity(self) -> FakeIdentityRepository:
        """Return the users, tokens, and role bindings repository."""
        return FakeIdentityRepository(self.scope.org_id, self._tenant)

    @property
    def audit(self) -> FakeAuditRepository:
        """Return the append-only audit repository."""
        return FakeAuditRepository(self.scope.org_id, self._tenant)

    @property
    def run_traces(self) -> FakeRunTraceStore:
        """Return the run, turn, tool-call, and evidence store."""
        return FakeRunTraceStore(self.scope.org_id, self._tenant)

    @property
    def sessions(self) -> FakeSessionStore:
        """Return the resumable session store."""
        return FakeSessionStore(self.scope.org_id, self._tenant)

    @property
    def episodes(self) -> FakeEpisodeStore:
        """Return the episodic memory store."""
        return FakeEpisodeStore(self.scope.org_id, self._tenant)

    @property
    def vectors(self) -> FakeVectorIndex:
        """Return the vector index."""
        return FakeVectorIndex(self.scope.org_id, self._tenant)

    @property
    def topology(self) -> FakeTopologyGraph:
        """Return the service topology graph."""
        return FakeTopologyGraph(self.scope.org_id, self._tenant, self.state)

    @property
    def knowledge(self) -> FakeKnowledgeStore:
        """Return the knowledge document and chunk store."""
        return FakeKnowledgeStore(self.scope.org_id, self._tenant)

    @property
    def approvals(self) -> FakeApprovalStore:
        """Return the approval and rollback-plan store."""
        return FakeApprovalStore(self.scope.org_id, self._tenant)

    @property
    def schedules(self) -> FakeScheduleStore:
        """Return the scheduled-job definitions store."""
        return FakeScheduleStore(self.scope.org_id, self._tenant)

    @property
    def credentials(self) -> FakeCredentialStore:
        """Return the encrypted credential store."""
        return FakeCredentialStore(self.scope.org_id, self._tenant)

    @property
    def estate(self) -> FakeEstateRepository:
        """Return the discovered-resource inventory and its health history."""
        return FakeEstateRepository(self.scope.org_id, self._tenant)

    @property
    def signals(self) -> FakeSignalStore:
        """Return the observation history the detectors read."""
        return FakeSignalStore(self.scope.org_id, self._tenant)

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising."""
        self._rollback_only = True

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""
        return self._rollback_only

    @property
    def _tenant(self) -> TenantState:
        """Return this unit's slice of the snapshot.

        Every repository above reads it through here, so there is exactly one
        expression in this package that turns a scope into storage — which is
        what makes "a repository cannot reach another tenant" checkable by
        reading one line rather than thirteen.
        """
        return self.state.tenant(self.scope.org_id)


@dataclass(slots=True)
class FakeSystemUnitOfWork:
    """The cross-tenant operations over one snapshot."""

    state: State
    _rollback_only: bool = field(default=False, repr=False)

    @property
    def orgs(self) -> OrgDirectory:
        """Return the organisation directory."""
        return FakeOrgDirectory(self.state)

    @property
    def tokens(self) -> TokenDirectory:
        """Return token resolution."""
        return FakeTokenDirectory(self.state)

    @property
    def jobs(self) -> JobDispatcher:
        """Return the cross-tenant job dispatcher."""
        return FakeJobDispatcher(self.state)

    @property
    def retention(self) -> RetentionSweeper:
        """Return the retention sweeper."""
        return FakeRetentionSweeper(self.state)

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising."""
        self._rollback_only = True

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""
        return self._rollback_only


class FakePersistence:
    """A complete ``PersistenceGateway`` that keeps everything in memory.

    Downstream features hold this in their unit tests exactly as they would hold
    the Postgres gateway in production — same protocol, same transactions, same
    errors — so a test that passes here is testing the code under test rather
    than a mock of its collaborator.
    """

    def __init__(self, *, topology_available: bool = True) -> None:
        self._state = State(topology_available=topology_available)
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def state(self) -> State:
        """Return the committed state, for a test that wants to look directly.

        Reading is fine. Writing through this bypasses the transaction machinery
        and is how a test comes to pass against a state no unit of work could
        have produced.
        """
        return self._state

    def set_topology_available(self, available: bool, *, reason: str | None = None) -> None:
        """Turn topology on or off, to exercise the FR-002 degradation path."""
        self._state.topology_available = available
        if reason is not None:
            self._state.topology_unavailable_reason = reason

    @asynccontextmanager
    async def begin(self, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
        """Open a transaction bound to ``scope``."""
        async with self._lock:
            if scope.org_id not in self._state.organisations:
                raise RecordNotFound(kind="organisation", identifier=scope.org_id)

            working = deepcopy(self._state)
            working.tenant(scope.org_id)
            unit = FakeUnitOfWork(scope=scope, state=working)
            yield unit
            if not unit.is_rollback_only:
                self._state = working

    @asynccontextmanager
    async def begin_system(self) -> AsyncIterator[SystemUnitOfWork]:
        """Open a transaction for the operations that have no tenant yet."""
        async with self._lock:
            working = deepcopy(self._state)
            unit = FakeSystemUnitOfWork(state=working)
            yield unit
            if not unit.is_rollback_only:
                self._state = working

    async def health(self) -> StoreHealth:
        """Return connectivity, extension, and migration status."""
        return summarise(
            connected=not self._closed,
            extensions=(
                ExtensionStatus(name="vector", available=True, version="in-memory"),
                ExtensionStatus(
                    name="age",
                    available=self._state.topology_available,
                    version="in-memory" if self._state.topology_available else None,
                ),
            ),
            migrations=MigrationStatus(
                head_revision=FAKE_HEAD_REVISION,
                applied_revision=FAKE_HEAD_REVISION,
            ),
            failure=None if not self._closed else "The in-memory store has been closed.",
        )

    async def close(self) -> None:
        """Release the connection pool. Idempotent."""
        self._closed = True


if TYPE_CHECKING:

    def _fakes_conform(
        gateway: FakePersistence,
        unit: FakeUnitOfWork,
        system: FakeSystemUnitOfWork,
    ) -> tuple[PersistenceGateway, UnitOfWork, SystemUnitOfWork]:
        """Fail ``make typecheck`` when a fake drifts from the port it stands in for.

        Never called, and never needs to be. Its value is that mypy checks the
        three returns structurally, so adding a method to a port without adding
        it here breaks the build with the signature that disagreed — rather
        than at whichever downstream feature happened to call it first.
        """
        return gateway, unit, system


__all__ = ["FakePersistence", "FakeSystemUnitOfWork", "FakeUnitOfWork"]
