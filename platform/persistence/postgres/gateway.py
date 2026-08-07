"""The PostgreSQL gateway, and the units of work it opens.

One ``AsyncSession`` per unit of work, one transaction per session, and every
repository the unit hands out bound to that same session. Leaving the block
commits; raising inside it rolls back — which is what makes SC-001's four-way
write atomic without any repository knowing the other three exist.

The graph is the one thing prepared eagerly rather than lazily. Apache AGE needs
``LOAD`` on the connection before Cypher will plan, and a repository that loaded
it on first use would have a different failure mode depending on whether the
caller happened to touch topology first. So ``begin`` does it once, records what
it found, and hands that verdict to the topology repository — which is also how
FR-002's degradation reaches a caller as ``TopologyUnavailable`` rather than as
a driver error nobody can act on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from platform.persistence.errors import RecordNotFound
from platform.persistence.health import summarise
from platform.persistence.ports.health import StoreHealth
from platform.persistence.ports.transaction import SystemUnitOfWork, TenantScope, UnitOfWork
from platform.persistence.postgres import migrations
from platform.persistence.postgres.crypto import KEY_RING
from platform.persistence.postgres.engine import (
    check_connectivity,
    connection,
    create_engine,
    probe_server,
)
from platform.persistence.postgres.graph import bootstrap
from platform.persistence.postgres.repositories.approval_store import PostgresApprovalStore
from platform.persistence.postgres.repositories.audit_repository import PostgresAuditRepository
from platform.persistence.postgres.repositories.config_repository import (
    PostgresConfigRepository,
    PostgresOrgDirectory,
)
from platform.persistence.postgres.repositories.credential_store import PostgresCredentialStore
from platform.persistence.postgres.repositories.episode_store import PostgresEpisodeStore
from platform.persistence.postgres.repositories.identity_repository import (
    PostgresIdentityRepository,
    PostgresTokenDirectory,
)
from platform.persistence.postgres.repositories.knowledge_store import PostgresKnowledgeStore
from platform.persistence.postgres.repositories.retention import PostgresRetentionSweeper
from platform.persistence.postgres.repositories.run_trace_store import PostgresRunTraceStore
from platform.persistence.postgres.repositories.schedule_store import (
    PostgresJobDispatcher,
    PostgresScheduleStore,
)
from platform.persistence.postgres.repositories.session_store import PostgresSessionStore
from platform.persistence.postgres.repositories.topology_graph import PostgresTopologyGraph
from platform.persistence.postgres.repositories.vector_index import PostgresVectorIndex


class _RollbackOnly(Exception):
    """Raised to make a unit of work roll back without the caller having raised.

    Never escapes this module. ``mark_rollback_only`` has to produce a rollback
    through the same path an exception does, because SQLAlchemy's transaction
    context commits on a clean exit and rolling back by hand first leaves it
    committing an inactive transaction.
    """


@dataclass(slots=True)
class PostgresUnitOfWork:
    """Twelve repositories over one session and one tenant."""

    scope: TenantScope
    session: AsyncSession
    graph: bootstrap.GraphReadiness
    _rollback_only: bool = field(default=False, repr=False)

    @property
    def config(self) -> PostgresConfigRepository:
        """Return the hierarchy and configuration repository."""
        return PostgresConfigRepository(self.scope.org_id, self.session)

    @property
    def identity(self) -> PostgresIdentityRepository:
        """Return the users, tokens, and role bindings repository."""
        return PostgresIdentityRepository(self.scope.org_id, self.session)

    @property
    def audit(self) -> PostgresAuditRepository:
        """Return the append-only audit repository."""
        return PostgresAuditRepository(self.scope.org_id, self.session)

    @property
    def run_traces(self) -> PostgresRunTraceStore:
        """Return the run, turn, tool-call, and evidence store."""
        return PostgresRunTraceStore(self.scope.org_id, self.session)

    @property
    def sessions(self) -> PostgresSessionStore:
        """Return the resumable session store."""
        return PostgresSessionStore(self.scope.org_id, self.session)

    @property
    def episodes(self) -> PostgresEpisodeStore:
        """Return the episodic memory store."""
        return PostgresEpisodeStore(self.scope.org_id, self.session)

    @property
    def vectors(self) -> PostgresVectorIndex:
        """Return the vector index."""
        return PostgresVectorIndex(self.scope.org_id, self.session)

    @property
    def topology(self) -> PostgresTopologyGraph:
        """Return the service topology graph."""
        return PostgresTopologyGraph(self.scope.org_id, self.session, self.graph)

    @property
    def knowledge(self) -> PostgresKnowledgeStore:
        """Return the knowledge document and chunk store."""
        return PostgresKnowledgeStore(self.scope.org_id, self.session)

    @property
    def approvals(self) -> PostgresApprovalStore:
        """Return the approval and rollback-plan store."""
        return PostgresApprovalStore(self.scope.org_id, self.session)

    @property
    def schedules(self) -> PostgresScheduleStore:
        """Return the scheduled-job definitions store."""
        return PostgresScheduleStore(self.scope.org_id, self.session)

    @property
    def credentials(self) -> PostgresCredentialStore:
        """Return the encrypted credential store."""
        return PostgresCredentialStore(self.scope.org_id, self.session)

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising."""
        self._rollback_only = True

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""
        return self._rollback_only


@dataclass(slots=True)
class PostgresSystemUnitOfWork:
    """The cross-tenant operations over one session."""

    session: AsyncSession
    _rollback_only: bool = field(default=False, repr=False)

    @property
    def orgs(self) -> PostgresOrgDirectory:
        """Return the organisation directory."""
        return PostgresOrgDirectory(self.session)

    @property
    def tokens(self) -> PostgresTokenDirectory:
        """Return token resolution."""
        return PostgresTokenDirectory(self.session)

    @property
    def jobs(self) -> PostgresJobDispatcher:
        """Return the cross-tenant job dispatcher."""
        return PostgresJobDispatcher(self.session)

    @property
    def retention(self) -> PostgresRetentionSweeper:
        """Return the retention sweeper."""
        return PostgresRetentionSweeper(self.session)

    def mark_rollback_only(self) -> None:
        """Ensure this unit rolls back when the block ends, without raising."""
        self._rollback_only = True

    @property
    def is_rollback_only(self) -> bool:
        """Return whether this unit is destined to roll back."""
        return self._rollback_only


class PostgresPersistence:
    """A ``PersistenceGateway`` over one PostgreSQL instance."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._graph: bootstrap.GraphReadiness | None = None
        self._closed = False

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> PostgresPersistence:
        """Return a gateway over a new engine for ``url``."""
        return cls(create_engine(url, echo=echo))

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying engine, for migrations and operational tooling."""
        return self._engine

    def migrator(self) -> migrations.AlembicSchemaMigrator:
        """Return this gateway's schema migrator, as the startup sequence's port.

        Offered here so a composition root that already names this backend does
        not also have to name the migrations module. The startup sequence holds
        the *policy* — order, skip handling, compatibility — and takes this as
        the thing that knows how to apply a revision.
        """
        return migrations.AlembicSchemaMigrator(self._engine)

    async def start(self) -> StoreHealth:
        """Bring the schema to head, load the encryption key, and report health.

        The one call an application makes at boot. Doing it as a method rather
        than in ``__init__`` is what lets the health it returns be *reported*
        instead of raised — a deployment missing Apache AGE should come up
        degraded and say so, not fail to construct its gateway.
        """
        KEY_RING.configure_from_environment()
        await migrations.upgrade_to_head(self._engine)
        await self._graph_readiness()
        return await self.health()

    @asynccontextmanager
    async def begin(self, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
        """Open a transaction bound to ``scope``."""
        graph = await self._graph_readiness()
        async with self._sessions() as session:
            try:
                async with session.begin():
                    if graph.available:
                        await bootstrap.load(await session.connection())

                    organisation = await PostgresOrgDirectory(session).get_organisation(
                        scope.org_id
                    )
                    if organisation is None:
                        raise RecordNotFound(kind="organisation", identifier=scope.org_id)

                    unit = PostgresUnitOfWork(scope=scope, session=session, graph=graph)
                    yield unit
                    if unit.is_rollback_only:
                        raise _RollbackOnly
            except _RollbackOnly:
                pass

    @asynccontextmanager
    async def begin_system(self) -> AsyncIterator[SystemUnitOfWork]:
        """Open a transaction for the operations that have no tenant yet."""
        async with self._sessions() as session:
            try:
                async with session.begin():
                    unit = PostgresSystemUnitOfWork(session=session)
                    yield unit
                    if unit.is_rollback_only:
                        raise _RollbackOnly
            except _RollbackOnly:
                pass

    async def _graph_readiness(self) -> bootstrap.GraphReadiness:
        """Return whether Cypher will run, creating the graph on first use.

        Cached for the life of the gateway. Creating a graph is DDL, and DDL
        inside a caller's unit of work would put a statement in their
        transaction that they did not ask for and cannot see.
        """
        if self._graph is None:
            self._graph = await bootstrap.ensure(self._engine)
        return self._graph

    async def health(self) -> StoreHealth:
        """Return connectivity, extension, and migration status (FR-023)."""
        if self._closed:
            return summarise(connected=False, failure="The gateway has been closed.")

        failure = await check_connectivity(self._engine)
        if failure is not None:
            return summarise(connected=False, failure=failure)

        try:
            async with connection(self._engine) as conn:
                facts = await probe_server(conn)
                revision = await migrations.applied_revision(conn)
                graph = await bootstrap.is_available(conn)
        except DBAPIError as error:
            return summarise(connected=False, failure=f"The database refused a probe: {error}")

        undecryptable = await self._undecryptable_credentials()

        return summarise(
            connected=True,
            server_version=facts.server_version,
            # AGE can be installed and still unusable — a graph that was never
            # created, a role that cannot LOAD it. What the health check reports
            # is whether Cypher would actually run, not whether a row exists in
            # ``pg_extension``.
            extensions=tuple(
                replace(status, available=graph.available) if status.name == "age" else status
                for status in facts.extensions
            ),
            migrations=migrations.status(revision),
            undecryptable_credentials=undecryptable,
            failure=None if graph.available else graph.reason,
        )

    async def close(self) -> None:
        """Release the connection pool. Idempotent."""
        if not self._closed:
            self._closed = True
            await self._engine.dispose()

    async def _undecryptable_credentials(self) -> tuple[str, ...]:
        """Return every handle in the deployment that will not open.

        Skipped entirely when no key is configured: a deployment that stores no
        credentials should not be reported as degraded for a key it will never
        use, and one that does store them fails at the first write instead.
        """
        if not KEY_RING.is_configured:
            return ()

        handles: list[str] = []
        async with self._sessions() as session, session.begin():
            for organisation in await PostgresOrgDirectory(session).list_organisations():
                store = PostgresCredentialStore(organisation.org_id, session)
                handles.extend(await store.verify_decryptable())
        return tuple(handles)


__all__ = ["PostgresPersistence", "PostgresSystemUnitOfWork", "PostgresUnitOfWork"]
