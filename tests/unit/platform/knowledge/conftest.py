"""Shared fixtures for the topology and knowledge-base suite.

Everything here is a real object rather than a mock. The gateway is the
in-memory persistence backend, which has real transactions and passes the same
contract suite as PostgreSQL; the embedder is the shipped local one; the
guardrail engine is the shipped default ruleset. The only double is a clock, so
a staleness assertion fails because the rule changed rather than because the
suite ran a week after the fixture was written.

Two teams and two organisations exist for every test, because "this team cannot
see that team's runbooks" is something to assert rather than assume.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope

PRIMARY_ORG = "acme"
SECOND_ORG = "globex"

PAYMENTS_TEAM = "team-payments"
SEARCH_TEAM = "team-search"

#: A fixed instant, so a verification-staleness assertion fails because the rule
#: changed rather than because the suite ran on an awkward day.
EPOCH = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def at(days: float = 0.0) -> datetime:
    """Return the fixed instant offset by ``days``."""
    return EPOCH + timedelta(days=days)


def frozen(days: float = 0.0) -> Clock:
    """Return a clock stuck at the fixed instant offset by ``days``."""
    return Clock(moment=at(days))


class Clock:
    """A callable that always returns the same instant.

    A class rather than a lambda so a test can move it — reconciliation is about
    what two runs at two different times do to one another, and a clock that
    could not be advanced would make that untestable.
    """

    __slots__ = ("moment",)

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        """Return the instant this clock is stuck at."""
        return self.moment

    def advance(self, days: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.moment = self.moment + timedelta(days=days)
        return self.moment


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with both organisations created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(PRIMARY_ORG, "Acme Corp")
        await system.orgs.create_organisation(SECOND_ORG, "Globex")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the team under test."""
    return TenantScope(org_id=PRIMARY_ORG, team_node_id=PAYMENTS_TEAM)


@pytest.fixture
def other_team_scope() -> TenantScope:
    """Return a second team in the same organisation."""
    return TenantScope(org_id=PRIMARY_ORG, team_node_id=SEARCH_TEAM)


@pytest.fixture
def other_org_scope() -> TenantScope:
    """Return a team in a different organisation."""
    return TenantScope(org_id=SECOND_ORG, team_node_id=PAYMENTS_TEAM)


@pytest.fixture
def clock() -> Clock:
    """Return a clock stuck at the fixed instant."""
    return frozen()


@pytest.fixture
def embedder() -> LocalEmbedder:
    """Return the shipped local embedder."""
    return LocalEmbedder()


@pytest.fixture
def engine() -> GuardrailEngine:
    """Return the guardrail engine over the shipped ruleset."""
    return GuardrailEngine()
