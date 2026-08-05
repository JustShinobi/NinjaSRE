"""Parameterises the persistence contract suite over every available backend.

FR-005 asks that every port have a suite any implementation must pass, so that
an alternative backend can be written without touching a caller. This file is
the mechanism: one ``gateway`` fixture, one row per backend, and every test
below runs once per row.

There are two rows. ``fakes`` always runs — it needs nothing. ``postgres`` runs
when a database is reachable, which is the case SC-005 actually asks about: the
same assertions, against pgvector and Apache AGE, with the in-memory
implementation held to exactly what the real one does.

When no database is reachable the suite still runs, against the fakes alone, and
``test_backends.py`` reports it. A run that exercised one backend has not shown
that the ports have two implementations, and that should be visible in the
output rather than in nobody's memory.

Two organisations are created for every test. One is the tenant under test; the
other exists so that "this port cannot see another tenant's records" is
something to assert rather than assume.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from postgres_backend import Backend, build_gateway, discover, scratch_database, stop_container

from config.constants.persistence import NINJASRE_TEST_DATABASE_URL_ENV
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope

PRIMARY_ORG = "acme"
SECOND_ORG = "globex"

FAKES = "fakes"
POSTGRES = "postgres"

#: A fixed instant, so an ordering assertion fails because the ordering changed
#: rather than because two records landed in the same microsecond.
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the flag that turns the PostgreSQL backend on."""
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="also run the persistence contract suite against a real PostgreSQL",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Discover a PostgreSQL once per session, before any test asks for one.

    Off unless asked for. The suite starts a container and creates a database
    per test, which is a minute the main gate should not spend on every commit —
    the plan puts it on a CI job of its own. ``NINJASRE_TEST_DATABASE_URL`` turns
    it on too, because an operator who went to the trouble of pointing the suite
    at a database meant for it to be used.
    """
    wanted = config.getoption("--postgres") or bool(os.environ.get(NINJASRE_TEST_DATABASE_URL_ENV))
    config.stash[_BACKEND_KEY] = discover() if wanted else None


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the container this session started, if it started one."""
    backend = config.stash.get(_BACKEND_KEY, None)
    if backend is not None and backend.source == "docker":
        stop_container()


_BACKEND_KEY: pytest.StashKey[Backend | None] = pytest.StashKey()


def _postgres_backend(config: pytest.Config) -> Backend | None:
    return config.stash.get(_BACKEND_KEY, None)


def postgres_backend_url(config: pytest.Config) -> str:
    """Return the server URL the suite discovered, for a test that needs a second database."""
    backend = _postgres_backend(config)
    assert backend is not None, "no PostgreSQL was discovered for this session"
    return backend.url


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parameterise every test that takes a ``gateway`` over the available backends."""
    if "gateway" not in metafunc.fixturenames:
        return
    backends = [FAKES]
    if _postgres_backend(metafunc.config) is not None:
        backends.append(POSTGRES)
    metafunc.parametrize("backend_name", backends, ids=backends, indirect=True)


@pytest.fixture
def backend_name(request: pytest.FixtureRequest) -> str:
    """Return the backend this test is running against."""
    return str(request.param)


@pytest.fixture
async def gateway(
    request: pytest.FixtureRequest, backend_name: str
) -> AsyncIterator[PersistenceGateway]:
    """Yield a gateway with two organisations already created."""
    if backend_name == FAKES:
        store: PersistenceGateway = FakePersistence()
        await _seed(store)
        yield store
        await store.close()
        return

    backend = _postgres_backend(request.config)
    assert backend is not None, "postgres was parameterised without a discovered backend"

    # A database per test, not per session. The alternative is truncating
    # twenty tables between tests and getting one of them wrong.
    async with scratch_database(backend) as url:
        postgres = await build_gateway(url)
        await _seed(postgres)
        yield postgres
        await postgres.close()


async def _seed(store: PersistenceGateway) -> None:
    """Create the two organisations every test starts from."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation(PRIMARY_ORG, "Acme Corp")
        await system.orgs.create_organisation(SECOND_ORG, "Globex")


@pytest.fixture
def scope() -> TenantScope:
    """Return the scope of the tenant under test."""
    return TenantScope(org_id=PRIMARY_ORG)


@pytest.fixture
def other_scope() -> TenantScope:
    """Return the scope of the tenant that must never be visible from the first."""
    return TenantScope(org_id=SECOND_ORG)
