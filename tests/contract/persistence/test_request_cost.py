"""What a request pays the database before it asks anything of its own.

Measured on a staging deployment where one round trip costs about a
millisecond: an authenticated request that read nothing of its own still
opened two units of work and made fifteen round trips, and the liveness probe
made five. Every one of them was a statement this package added on the
caller's behalf — an organisation lookup and a graph library load per
transaction, a full server probe per health report. These tests hold each of
those to the count it is now allowed.

PostgreSQL only: the in-memory store has no statements to count.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from conftest import POSTGRES
from sqlalchemy import event, text

from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.postgres.gateway import PostgresPersistence, PostgresUnitOfWork

pytestmark = [pytest.mark.contract, pytest.mark.usefixtures("postgres_only")]


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip the in-memory backend: there are no statements there to count."""
    if backend_name != POSTGRES:
        pytest.skip("counts statements, which only PostgreSQL sends")


@contextmanager
def statements(gateway: PostgresPersistence) -> Iterator[list[str]]:
    """Collect every statement the engine sends while the block runs."""
    seen: list[str] = []

    def record(conn: object, cursor: object, statement: str, *rest: object) -> None:
        del conn, cursor, rest
        seen.append(" ".join(statement.split()))

    engine = gateway.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def test_a_unit_of_work_on_a_known_organisation_asks_the_database_nothing(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The organisation was looked up once; the next transaction trusts that."""
    assert isinstance(gateway, PostgresPersistence)
    async with gateway.begin(scope):
        pass

    with statements(gateway) as seen:
        async with gateway.begin(scope):
            pass

    assert seen == [], f"a unit of work on a known organisation still sent {seen}"


async def test_an_organisation_nobody_created_is_still_refused(
    gateway: PersistenceGateway,
) -> None:
    """The lookup is deferred, never dropped."""
    with pytest.raises(RecordNotFound):
        async with gateway.begin(TenantScope(org_id="nobody-made-this")):
            pass


async def test_the_graph_library_is_loaded_once_per_connection_not_per_transaction(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Cypher works inside a unit of work that never issued ``LOAD`` itself."""
    assert isinstance(gateway, PostgresPersistence)
    if not (await gateway.health()).is_ready:
        pytest.skip("the server has no usable graph library")

    with statements(gateway) as seen:
        async with gateway.begin(scope) as uow:
            assert isinstance(uow, PostgresUnitOfWork)
            count = await uow.session.scalar(text("SELECT count(*) FROM ag_catalog.ag_graph"))

    assert count is not None
    assert not [s for s in seen if s.upper().startswith("LOAD")], seen


async def test_a_second_health_report_within_the_window_only_checks_connectivity(
    gateway: PersistenceGateway,
) -> None:
    """Liveness stays live; the facts that change only at a deploy are reused."""
    assert isinstance(gateway, PostgresPersistence)
    first = await gateway.health()

    with statements(gateway) as seen:
        second = await gateway.health()

    assert second == first
    assert seen == ["SELECT 1"], f"a reused health report still sent {seen}"
