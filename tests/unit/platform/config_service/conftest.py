"""Shared fixtures for the configuration service suite.

Everything is a real object. The gateway is the in-memory persistence backend,
which has real transactions and passes the same contract suite as PostgreSQL,
and the guardrail engine is the shipped default ruleset — a secret-rejection
test that ran against a hand-written pattern would prove only that the pattern
matched itself.

Two organisations exist for every test, because "this team cannot resolve that
organisation's configuration" is something to assert rather than assume.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from platform.config_service.document import NodeDocument
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)

PRIMARY_ORG = "acme"
SECOND_ORG = "globex"

DIVISION = "division-platform"
TEAM = "team-payments"
SQUAD = "squad-checkout"
OTHER_TEAM = "team-search"

#: The four-level chain SC-001 and SC-003 are stated against, root first. The
#: organisation's root node carries the organisation's own id.
FOUR_LEVELS: tuple[tuple[str, str | None, ConfigNodeKind], ...] = (
    (PRIMARY_ORG, None, ConfigNodeKind.ORGANISATION),
    (DIVISION, PRIMARY_ORG, ConfigNodeKind.TEAM),
    (TEAM, DIVISION, ConfigNodeKind.TEAM),
    (SQUAD, TEAM, ConfigNodeKind.SERVICE),
)


async def write_node(
    gateway: PersistenceGateway,
    scope: TenantScope,
    node_id: str,
    *,
    parent_id: str | None,
    kind: ConfigNodeKind = ConfigNodeKind.TEAM,
    settings: Mapping[str, Any] | None = None,
    locked: tuple[str, ...] = (),
) -> ConfigNode:
    """Store one node's document directly, bypassing validation.

    Tests of merge, provenance, and caching are about what happens *after* a
    write, and going through the service would make every one of them also a
    test of the schema. The write paths have their own suite.
    """
    document = NodeDocument.of(settings or {}, locked=locked)
    async with gateway.begin(scope) as uow:
        existing = await uow.config.get(node_id)
        node = ConfigNode(
            node_id=node_id,
            kind=kind,
            name=node_id,
            parent_id=parent_id,
            values=document.to_values(),
            version=existing.version if existing is not None else 0,
        )
        return await uow.config.upsert(node)


@pytest.fixture
async def four_levels(gateway: PersistenceGateway, scope: TenantScope) -> tuple[str, ...]:
    """Create the four-level chain with no configuration on any node."""
    for node_id, parent_id, kind in FOUR_LEVELS:
        await write_node(gateway, scope, node_id, parent_id=parent_id, kind=kind)
    return tuple(node_id for node_id, _, _ in FOUR_LEVELS)


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
    """Return the organisation under test."""
    return TenantScope(org_id=PRIMARY_ORG)


@pytest.fixture
def other_org_scope() -> TenantScope:
    """Return the second organisation."""
    return TenantScope(org_id=SECOND_ORG)


@pytest.fixture
def engine() -> GuardrailEngine:
    """Return the guardrail engine over the shipped ruleset."""
    return GuardrailEngine()
