"""The unit of work: one tenant, one transaction, and every repository inside it.

Acceptance scenario 2 asks that a trace, an episode, an embedding, and a set of
topology edges commit together or not at all. That requirement decides the shape
of this module, because there are only two ways to give a caller composable
atomicity and one of them is bad.

The bad one is a transaction handle threaded through every write — twelve ports,
sixty methods, an extra parameter on each, and a caller who forgets it on one
call gets an autocommit that silently escapes the transaction. The failure is
invisible until a rollback does not roll something back.

So: **repositories come from the unit of work**, and a repository obtained from
one is already inside its transaction. There is no way to hold a repository that
is not in a transaction, because there is nowhere else to get one.

    async with gateway.begin(scope) as uow:
        await uow.run_traces.record_evidence(evidence)
        await uow.episodes.save(episode)
        await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector])
        await uow.topology.upsert_edge(edge)

Leaving the block commits; raising inside it rolls back. There is no ``commit``
to forget and no way to commit a unit that has already failed.

**Tenancy comes from the scope, not from arguments.** The unit of work is opened
for one organisation and every repository it hands out is bound to that
organisation. Look through the twelve ports and no method takes an ``org_id`` —
so FR-010 is satisfied not by a check that rejects cross-tenant reads but by
there being no way to phrase one. A test can still prove it, and does, by
opening two scopes and looking for the other's records.

The operations that genuinely cannot know their tenant — resolving a token,
claiming due jobs, creating an organisation, sweeping retention — are the
``SystemUnitOfWork``, and keeping them in one small enumerable place is what
makes the guarantee above true rather than nearly true.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from platform.persistence.ports.approval_store import ApprovalStore
from platform.persistence.ports.audit_repository import AuditRepository
from platform.persistence.ports.config_repository import ConfigRepository, OrgDirectory
from platform.persistence.ports.credential_store import CredentialStore
from platform.persistence.ports.episode_store import EpisodeStore
from platform.persistence.ports.health import StoreHealth
from platform.persistence.ports.identity_repository import IdentityRepository, TokenDirectory
from platform.persistence.ports.knowledge_store import KnowledgeStore
from platform.persistence.ports.retention import RetentionSweeper
from platform.persistence.ports.run_trace_store import RunTraceStore
from platform.persistence.ports.schedule_store import JobDispatcher, ScheduleStore
from platform.persistence.ports.session_store import SessionStore
from platform.persistence.ports.topology_graph import TopologyGraph
from platform.persistence.ports.vector_index import VectorIndex


@dataclass(frozen=True, slots=True)
class TenantScope:
    """The organisation, and optionally the node, a unit of work is opened for.

    ``team_node_id`` narrows reads that are node-scoped — a team's config, a
    team's scheduled jobs — and is ignored by ports whose records belong to the
    organisation as a whole. It is never a second security boundary: within an
    organisation, narrowing is a convenience, and the boundary that matters is
    ``org_id``.
    """

    org_id: str
    team_node_id: str | None = None

    def __post_init__(self) -> None:
        if not self.org_id:
            raise ValueError("A tenant scope needs an organisation id.")

    def narrowed_to(self, team_node_id: str) -> TenantScope:
        """Return this scope narrowed to a node within the same organisation."""
        return TenantScope(org_id=self.org_id, team_node_id=team_node_id)


@runtime_checkable
class UnitOfWork(Protocol):
    """Every tenant-scoped repository, inside one transaction.

    Twelve properties and one method. The properties are the ports; the method
    is the escape hatch for a caller that decides mid-unit to abandon its work
    without raising, which happens when "nothing to do after all" is a normal
    outcome rather than an error.
    """

    @property
    def scope(self) -> TenantScope:
        """Return the tenant this unit of work is bound to."""

    @property
    def config(self) -> ConfigRepository:
        """Return the hierarchy and configuration repository."""

    @property
    def identity(self) -> IdentityRepository:
        """Return the users, tokens, and role bindings repository."""

    @property
    def audit(self) -> AuditRepository:
        """Return the append-only audit repository."""

    @property
    def run_traces(self) -> RunTraceStore:
        """Return the run, turn, tool-call, and evidence store."""

    @property
    def sessions(self) -> SessionStore:
        """Return the resumable session store."""

    @property
    def episodes(self) -> EpisodeStore:
        """Return the episodic memory store."""

    @property
    def vectors(self) -> VectorIndex:
        """Return the vector index."""

    @property
    def topology(self) -> TopologyGraph:
        """Return the service topology graph."""

    @property
    def knowledge(self) -> KnowledgeStore:
        """Return the knowledge document and chunk store."""

    @property
    def approvals(self) -> ApprovalStore:
        """Return the approval and rollback-plan store."""

    @property
    def schedules(self) -> ScheduleStore:
        """Return the scheduled-job definitions store."""

    @property
    def credentials(self) -> CredentialStore:
        """Return the encrypted credential store."""

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising.

        Idempotent. Once marked, a unit cannot be un-marked: the caller has
        already decided its writes are not wanted, and letting something later
        in the same block reverse that decision would make the outcome depend
        on ordering nobody wrote down.
        """

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""


@runtime_checkable
class SystemUnitOfWork(Protocol):
    """The operations that precede or span tenancy, inside one transaction.

    Four, and each is here because it genuinely cannot name a tenant in
    advance: you cannot scope to an organisation you are creating, resolving a
    token is how the tenant becomes known, a worker asks what is due across
    every tenant at once, and retention is a property of the deployment.

    Anything proposed for this interface should first be asked why it does not
    already have a scope. The answer is usually that its caller lost one.
    """

    @property
    def orgs(self) -> OrgDirectory:
        """Return the organisation directory."""

    @property
    def tokens(self) -> TokenDirectory:
        """Return token resolution."""

    @property
    def jobs(self) -> JobDispatcher:
        """Return the cross-tenant job dispatcher."""

    @property
    def retention(self) -> RetentionSweeper:
        """Return the retention sweeper."""

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising."""

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""


@runtime_checkable
class PersistenceGateway(Protocol):
    """Where units of work come from, and the only thing a caller holds.

    Long-lived: one per process, holding the connection pool. Everything else
    in this package is reached through a unit of work opened from here, which
    is what makes "no repository exists outside a transaction" true of the
    whole layer rather than of most of it.
    """

    def begin(self, scope: TenantScope) -> AbstractAsyncContextManager[UnitOfWork]:
        """Open a transaction bound to ``scope``.

        Commits when the block exits normally, rolls back when it raises or
        when the unit was marked rollback-only.
        """

    def begin_system(self) -> AbstractAsyncContextManager[SystemUnitOfWork]:
        """Open a transaction for the operations that have no tenant yet."""

    async def health(self) -> StoreHealth:
        """Return connectivity, extension, and migration status (FR-023).

        Never raises. A health check that throws when the store is down reports
        nothing about the store being down.
        """

    async def close(self) -> None:
        """Release the connection pool. Idempotent."""


__all__ = [
    "PersistenceGateway",
    "SystemUnitOfWork",
    "TenantScope",
    "UnitOfWork",
]
