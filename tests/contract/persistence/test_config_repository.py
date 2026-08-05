"""Contract: the hierarchy and the configuration layered onto it."""

from __future__ import annotations

import pytest
from conftest import PRIMARY_ORG

from platform.persistence.errors import (
    ConcurrentModification,
    DuplicateRecord,
    RecordNotFound,
    ReferencedRecord,
)
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)

pytestmark = pytest.mark.contract


def team(node_id: str, *, parent: str, name: str = "") -> ConfigNode:
    """Return a team node under ``parent``."""
    return ConfigNode(
        node_id=node_id,
        kind=ConfigNodeKind.TEAM,
        name=name or node_id,
        parent_id=parent,
    )


async def test_the_root_node_is_the_organisation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        root = await uow.config.root()

    assert root.node_id == PRIMARY_ORG
    assert root.kind is ConfigNodeKind.ORGANISATION
    assert root.parent_id is None


async def test_upserting_a_node_returns_it_at_the_next_version(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        stored = await uow.config.upsert(team("payments", parent=PRIMARY_ORG))

    assert stored.version == 1
    assert stored.updated_at is not None


async def test_a_stale_version_is_refused_rather_than_merged(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        first = await uow.config.upsert(team("payments", parent=PRIMARY_ORG))
        await uow.config.upsert(first)

        with pytest.raises(ConcurrentModification) as failure:
            await uow.config.upsert(first)

    assert failure.value.expected == 1
    assert failure.value.found == 2


async def test_a_node_under_an_unknown_parent_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.config.upsert(team("payments", parent="no-such-team"))


async def test_children_come_back_ordered_by_name(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.config.upsert(team("z", parent=PRIMARY_ORG, name="zulu"))
        await uow.config.upsert(team("a", parent=PRIMARY_ORG, name="alpha"))
        children = await uow.config.children(PRIMARY_ORG)

    assert [node.name for node in children] == ["alpha", "zulu"]


async def test_ancestors_are_root_first_and_include_the_node(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.config.upsert(team("payments", parent=PRIMARY_ORG))
        await uow.config.upsert(
            ConfigNode(
                node_id="checkout",
                kind=ConfigNodeKind.SERVICE,
                name="checkout",
                parent_id="payments",
            )
        )
        path = await uow.config.ancestors("checkout")

    # The deep merge consumes this order: most general first, each descendant
    # overriding what it names.
    assert [node.node_id for node in path] == [PRIMARY_ORG, "payments", "checkout"]


async def test_a_node_with_children_is_not_deleted_out_from_under_them(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.config.upsert(team("payments", parent=PRIMARY_ORG))
        await uow.config.upsert(
            ConfigNode(
                node_id="checkout",
                kind=ConfigNodeKind.SERVICE,
                name="checkout",
                parent_id="payments",
            )
        )

        with pytest.raises(ReferencedRecord):
            await uow.config.delete("payments")


async def test_deleting_a_leaf_reports_whether_it_was_there(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.config.upsert(team("payments", parent=PRIMARY_ORG))

        assert await uow.config.delete("payments") is True
        assert await uow.config.delete("payments") is False


async def test_an_organisation_id_is_claimed_once(gateway: PersistenceGateway) -> None:
    async with gateway.begin_system() as system:
        with pytest.raises(DuplicateRecord):
            await system.orgs.create_organisation(PRIMARY_ORG, "Acme Again")


async def test_opening_a_scope_for_an_unknown_organisation_fails(
    gateway: PersistenceGateway,
) -> None:
    # Not a permissions decision — there is nothing to be permitted. A caller
    # holding a scope for an organisation that does not exist has a bug
    # upstream, and finding out at ``begin`` names it.
    with pytest.raises(RecordNotFound):
        async with gateway.begin(TenantScope(org_id="nowhere")):
            pass
