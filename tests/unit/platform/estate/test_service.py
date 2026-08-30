"""`EstateService`'s own reads, above the repository port.

Two claims live here rather than in the persistence contract suite because
both need the kind registry `EstateService` carries and the repository does
not: resolving a parent's name is a service-level join, and `unhealthy_since`
is served on `ResourceView`, which is this module's own type.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.estate.kinds import core_registry
from platform.estate.service import EstateService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EstateQuery,
    HealthDerivation,
    PersistenceGateway,
    Resource,
    ResourceHealth,
    TenantScope,
)

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    return EPOCH + timedelta(minutes=minutes)


def derivation(state: ResourceHealth, *, minutes: float = 0.0) -> HealthDerivation:
    return HealthDerivation(state=state, rule="provider_status", derived_at=at(minutes))


def guest(resource_id: str, *, parent_id: str | None) -> Resource:
    return Resource(
        resource_id=resource_id,
        kind="container",
        source="proxmox",
        native_id=resource_id,
        display_name=resource_id,
        parent_id=parent_id,
        first_seen_at=at(),
        last_seen_at=at(),
    )


def node(resource_id: str, *, display_name: str) -> Resource:
    return Resource(
        resource_id=resource_id,
        kind="node",
        source="proxmox",
        native_id=resource_id,
        display_name=display_name,
        first_seen_at=at(),
        last_seen_at=at(),
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


@pytest.fixture
def scope() -> TenantScope:
    return TenantScope(org_id=ORG)


@pytest.fixture
def service(gateway: PersistenceGateway) -> EstateService:
    return EstateService(gateway=gateway, kinds=core_registry())


async def test_a_listing_resolves_the_parent_name_even_when_the_parent_is_off_the_page(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-006: `parent_name` must not depend on the parent sharing the page.

    A query filtered to `unhealthy` returns none of this deployment's (healthy)
    nodes, so the parent never rode along in the same page the old code only
    ever consulted. The listing must still resolve the node's own name.
    """
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(node("node-pve01", display_name="pve01"))
        await uow.estate.upsert(guest("ct-100", parent_id="node-pve01"))
        await uow.estate.record_health("ct-100", derivation(ResourceHealth.UNHEALTHY))

    found = await service.query(scope, EstateQuery(health=(ResourceHealth.UNHEALTHY,)), now=at())

    assert len(found) == 1
    assert found[0].resource.resource_id == "ct-100"
    assert found[0].parent_name == "pve01"


async def test_a_resource_with_no_parent_carries_no_parent_name(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(guest("ct-101", parent_id=None))

    found = await service.query(scope, EstateQuery(), now=at())

    assert found[0].parent_name == ""


async def test_an_unhealthy_resource_carries_when_its_current_streak_began(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(guest("ct-100", parent_id=None))
        await uow.estate.record_health("ct-100", derivation(ResourceHealth.HEALTHY, minutes=0))
        await uow.estate.record_health("ct-100", derivation(ResourceHealth.UNHEALTHY, minutes=30))

    found = await service.query(scope, EstateQuery(health=(ResourceHealth.UNHEALTHY,)), now=at(45))

    assert found[0].unhealthy_since == at(30)


async def test_a_healthy_resource_carries_no_unhealthy_since(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(guest("ct-102", parent_id=None))
        await uow.estate.record_health("ct-102", derivation(ResourceHealth.HEALTHY))

    found = await service.query(scope, EstateQuery(), now=at())

    assert found[0].unhealthy_since is None
