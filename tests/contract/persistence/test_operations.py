"""SC-007 and SC-008, plus the two operational promises nothing else checks.

These are the tests an operator's confidence rests on, and every one of them is
about a moment that only happens once things have gone wrong: restoring a
backup, rolling back a release, discovering that a key did not survive a move.

They run against PostgreSQL only. There is no in-memory equivalent of a
``pg_dump``, and pretending otherwise would be a test that proves nothing about
the thing it is named after.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import POSTGRES, PRIMARY_ORG, at, postgres_backend_url
from postgres_backend import (
    Backend,
    create_database,
    drop_database,
    dump_and_restore_available,
    dump_database,
    restore_database,
)
from sqlalchemy import text

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE, MIGRATION_TABLE_NAME
from platform.persistence.ports import (
    ActorKind,
    AgentRun,
    AuditEvent,
    CredentialMetadata,
    Episode,
    EvidenceRecord,
    PersistenceGateway,
    SecretValue,
    TenantScope,
    TopologyEdge,
    VectorRecord,
)
from platform.persistence.postgres import migrations
from platform.persistence.postgres.gateway import PostgresPersistence, PostgresUnitOfWork

pytestmark = pytest.mark.contract

SECRET = "xoxb-not-a-real-slack-token-000"
HANDLE = "slack-bot-token"


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip a test that has no meaning without a real database."""
    if backend_name != POSTGRES:
        pytest.skip("Backups, migrations, and at-rest encryption are PostgreSQL's.")


async def seed(gateway: PersistenceGateway, scope: TenantScope) -> None:
    """Write one representative record of every shape the schema holds."""
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(AgentRun(run_id="run-1", trigger="alert", started_at=at()))
        await uow.run_traces.record_evidence(
            EvidenceRecord(
                evidence_id="e-1",
                run_id="run-1",
                source="prometheus",
                evidence_type="metric",
                observed_at=at(1),
                body={"value": 42},
            )
        )
        await uow.episodes.save(
            Episode(
                episode_id="ep-1",
                title="Checkout 5xx",
                summary="Pool exhaustion.",
                signature="checkout-5xx",
                run_id="run-1",
                occurred_at=at(),
                components=("checkout",),
            )
        )
        await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model="m", dimension=3)
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [VectorRecord(vector_id="ep-1", embedding=(0.1, 0.2, 0.3))],
        )
        await uow.topology.upsert_edge(TopologyEdge(from_node_id="web", to_node_id="checkout"))
        await uow.audit.append(
            AuditEvent(
                event_id="a-1",
                occurred_at=at(),
                actor_kind=ActorKind.AGENT,
                actor_id="run-1",
                action="capability.invoke",
                resource_kind="deployment",
                resource_id="checkout",
            )
        )
        await uow.credentials.store(
            CredentialMetadata(handle=HANDLE, integration="slack"), SecretValue(SECRET)
        )


@pytest.mark.usefixtures("postgres_only")
async def test_migrations_roll_forward_and_back_over_seeded_data(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-008.

    A downgrade drops the tables, so the *data* does not survive — that is what
    a downgrade is. What has to survive is the operator's ability to do it: a
    schema change that cannot be reversed turns a bad release into an outage
    with no way back, and the way that fails is a ``downgrade`` nobody ran until
    the night it was needed.
    """
    assert isinstance(gateway, PostgresPersistence)
    await seed(gateway, scope)

    head = migrations.head_revision()
    async with gateway.engine.connect() as conn:
        assert await migrations.applied_revision(conn) == head

    await migrations.downgrade_to(gateway.engine, "base")
    async with gateway.engine.connect() as conn:
        assert await migrations.applied_revision(conn) is None
        remaining = await conn.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'agent_runs'"
            )
        )
    assert remaining == 0

    assert await migrations.upgrade_to_head(gateway.engine) == head

    # The schema is usable again, and empty — which is what a base-and-back
    # round trip should leave. The organisation has to be recreated because the
    # downgrade dropped its table, and that is the point being made.
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(scope.org_id, "Acme Corp")
    async with gateway.begin(scope) as uow:
        assert await uow.run_traces.list_runs() == ()
        assert await uow.episodes.count() == 0


@pytest.mark.usefixtures("postgres_only")
async def test_two_replicas_starting_together_do_not_race(
    gateway: PersistenceGateway,
) -> None:
    """FR-007's advisory lock.

    Both callers finish and both report head. Only one of them applied
    anything, which is the property a rolling deployment needs and the one a
    lock-free implementation loses under exactly this timing.
    """
    assert isinstance(gateway, PostgresPersistence)
    await migrations.downgrade_to(gateway.engine, "base")

    first, second = await asyncio.gather(
        migrations.upgrade_to_head(gateway.engine),
        migrations.upgrade_to_head(gateway.engine),
    )

    assert first == second == migrations.head_revision()


@pytest.mark.usefixtures("postgres_only")
async def test_a_backup_restores_into_a_clean_database_with_its_integrity(
    request: pytest.FixtureRequest, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-007 and FR-021."""
    if not dump_and_restore_available():
        pytest.skip("Neither pg_dump/psql on PATH nor a container to run them in.")

    assert isinstance(gateway, PostgresPersistence)
    await seed(gateway, scope)

    source_url = str(gateway.engine.url.render_as_string(hide_password=False))
    dump = dump_database(source_url)
    assert "CREATE TABLE" in dump

    backend = Backend(url=postgres_backend_url(request.config), source="restore-target")
    restored_name = "ninjasre_restored"
    restored_url = await create_database(backend, restored_name)

    try:
        restore_database(restored_url, dump)
        restored = PostgresPersistence.from_url(restored_url)
        try:
            async with restored.begin(scope) as uow:
                # Referential integrity: the trace and everything hanging off it.
                trace = await uow.run_traces.replay("run-1")
                assert [item.evidence_id for item in trace.evidence] == ["e-1"]
                assert trace.evidence[0].body == {"value": 42}

                # Vector integrity: the embedding survived, and still searches.
                assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 1
                matches = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (0.1, 0.2, 0.3), k=1)
                assert matches[0].vector_id == "ep-1"

                # The audit trail, which no retention pass may remove and no
                # restore may lose.
                assert await uow.audit.get("a-1") is not None

                # The credential, decrypted with the key the process holds —
                # which is the point: the key is *not* in the dump.
                assert (await uow.credentials.reveal(HANDLE)).reveal() == SECRET
        finally:
            await restored.close()
    finally:
        await drop_database(backend, restored_name)


@pytest.mark.usefixtures("postgres_only")
async def test_a_credential_is_ciphertext_in_the_table(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-018, checked by reading the bytes rather than trusting the column type.

    A dump, a replica, or an operator with a psql session sees an envelope. That
    is the whole claim, and the only way to check it is to look at what is
    actually stored.
    """
    async with gateway.begin(scope) as uow:
        await uow.credentials.store(
            CredentialMetadata(handle=HANDLE, integration="slack"), SecretValue(SECRET)
        )

    async with gateway.begin(scope) as uow:
        assert isinstance(uow, PostgresUnitOfWork)
        stored = await uow.session.scalar(
            text("SELECT secret FROM credentials WHERE org_id = :org AND handle = :handle"),
            {"org": PRIMARY_ORG, "handle": HANDLE},
        )

    assert isinstance(stored, bytes)
    assert SECRET.encode("utf-8") not in stored
    assert b"xoxb" not in stored
    # Round-trips through the port, so this is encryption rather than loss.
    async with gateway.begin(scope) as uow:
        assert (await uow.credentials.reveal(HANDLE)).reveal() == SECRET


@pytest.mark.usefixtures("postgres_only")
async def test_a_dump_contains_no_plaintext_credential(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The property an operator actually cares about: backups do not leak."""
    if not dump_and_restore_available():
        pytest.skip("Neither pg_dump/psql on PATH nor a container to run them in.")

    assert isinstance(gateway, PostgresPersistence)
    await seed(gateway, scope)

    dump = dump_database(str(gateway.engine.url.render_as_string(hide_password=False)))

    assert SECRET not in dump
    assert "xoxb" not in dump
    # The handle is in there, because a backup has to restore what is
    # configured. Only the value is protected.
    assert HANDLE in dump


@pytest.mark.usefixtures("postgres_only")
async def test_the_version_table_is_the_one_the_constant_names(
    gateway: PersistenceGateway,
) -> None:
    """A stray ``alembic_version`` would mean two records of what is applied."""
    assert isinstance(gateway, PostgresPersistence)
    async with gateway.engine.connect() as conn:
        ours = await conn.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :name"
            ),
            {"name": MIGRATION_TABLE_NAME},
        )
        alembics_own = await conn.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
            )
        )

    assert ours == 1
    assert alembics_own == 0
