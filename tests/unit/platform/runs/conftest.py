"""Shared fixtures for the run-trace suite.

Everything is real except the clock. The gateway is the in-memory persistence
backend, which has real transactions and passes the same contract suite as
PostgreSQL, so a recorder tested here is tested against the same behaviour it
gets in production. The clock is a counter because "the replayed view matches
the live one" is an assertion about ordering, and two records landing in the
same microsecond would make it fail for a reason nobody cares about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest

from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope, UnitOfWork

ORG = "acme"
TEAM = "team-payments"
PRINCIPAL = "ada"

#: A fixed instant, so an ordering assertion fails because the ordering changed.
EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def at(seconds: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``seconds``."""
    return EPOCH + timedelta(seconds=seconds)


@pytest.fixture
def clock() -> Callable[[], datetime]:
    """Return a clock that advances one second per reading."""
    ticks = iter(range(10_000))

    def now() -> datetime:
        return at(next(ticks))

    return now


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Return a persistence gateway holding one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, name="Acme")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the tenant scope every test in this suite opens."""
    return TenantScope(org_id=ORG, team_node_id=TEAM)


@pytest.fixture
async def uow(gateway: PersistenceGateway, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
    """Return one open unit of work, committed when the test ends."""
    async with gateway.begin(scope) as unit:
        yield unit
