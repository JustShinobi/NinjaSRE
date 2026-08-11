"""Shared fixtures for the proposal queue suite.

Everything is a real object. The gateway is the in-memory persistence backend,
which has real transactions and passes the same contract suite as PostgreSQL;
the configuration service is the shipped one, so a proposal that would fail
validation fails here for the reason it would fail in production.

The clock is the only double, and it is fixed rather than moving: an expiry
assertion has to fail because the rule changed, not because the suite ran at
23:59.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from platform.config_service.document import NodeDocument
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)

ORG = "acme"
TEAM = "team-payments"

#: A fixed instant, so an expiry assertion fails because the rule changed.
EPOCH = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def at(hours: float = 0.0) -> datetime:
    """Return the fixed instant offset by ``hours``."""
    return EPOCH + timedelta(hours=hours)


class Clock:
    """A callable stuck at one instant, movable by a test that needs two."""

    __slots__ = ("moment",)

    def __init__(self, moment: datetime | None = None) -> None:
        self.moment = moment if moment is not None else EPOCH

    def __call__(self) -> datetime:
        """Return the instant this clock is stuck at."""
        return self.moment

    def advance(self, hours: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.moment = self.moment + timedelta(hours=hours)
        return self.moment


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with the organisation and its team created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")
    scope = TenantScope(org_id=ORG)
    # The organisation's root node comes with the organisation. Only the team
    # beneath it is this suite's to create.
    async with store.begin(scope) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM,
                kind=ConfigNodeKind.TEAM,
                name=TEAM,
                parent_id=ORG,
                values=NodeDocument().to_values(),
            )
        )
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the team the review queue is scoped to."""
    return TenantScope(org_id=ORG, team_node_id=TEAM)


@pytest.fixture
def clock() -> Clock:
    """Return a clock stuck at the fixed instant."""
    return Clock()


@pytest.fixture
def engine() -> GuardrailEngine:
    """Return the guardrail engine over the shipped ruleset."""
    return GuardrailEngine()


@pytest.fixture
def config(gateway: PersistenceGateway, clock: Clock) -> ConfigService:
    """Return the shipped configuration service over the in-memory store."""
    return ConfigService(gateway=gateway, scope=TenantScope(org_id=ORG), clock=clock)


async def settings_of(gateway: PersistenceGateway, node_id: str = TEAM) -> Mapping[str, Any]:
    """Return what ``node_id`` declares of its own, straight from the store."""
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        node = await uow.config.get(node_id)
    assert node is not None
    return NodeDocument.of_node(node).settings
