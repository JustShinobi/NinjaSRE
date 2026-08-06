"""SC-005 and SC-006: what a node resolves to, where each value came from, and
what makes a cached answer stop being the answer.

The invalidation test is the one that matters. A configuration cache that serves
a stale value serves it during the incident the change was made for, and the
symptom — an agent running on the model the platform team switched away from an
hour ago — is invisible in every log.
"""

from __future__ import annotations

import pytest

from platform.config_service.effective import EffectiveConfigResolver
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.config_service.conftest import (
    DIVISION,
    PRIMARY_ORG,
    SQUAD,
    TEAM,
    write_node,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def resolver(gateway: PersistenceGateway, scope: TenantScope) -> EffectiveConfigResolver:
    return EffectiveConfigResolver(gateway=gateway, scope=scope)


async def test_a_node_resolves_to_its_ancestors_merged_with_its_own(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    await write_node(
        gateway, scope, PRIMARY_ORG, parent_id=None, settings={"models": {"investigator": "opus"}}
    )
    await write_node(
        gateway, scope, TEAM, parent_id=DIVISION, settings={"models": {"investigator": "sonnet"}}
    )

    effective = await resolver.resolve(SQUAD)

    assert effective.value_at("models.investigator") == "sonnet"


async def test_every_resolved_value_names_the_node_that_supplied_it(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    """SC-005."""
    await write_node(gateway, scope, PRIMARY_ORG, parent_id=None, settings={"a": 1, "b": 2})
    await write_node(gateway, scope, DIVISION, parent_id=PRIMARY_ORG, settings={"b": 3})
    await write_node(gateway, scope, SQUAD, parent_id=TEAM, settings={"c": 4})

    effective = await resolver.resolve(SQUAD)

    assert effective.source_of("a") == PRIMARY_ORG
    assert effective.source_of("b") == DIVISION
    assert effective.source_of("c") == SQUAD
    assert all(effective.source_of(path) for path in effective.provenance)


async def test_an_unset_path_names_no_source(
    four_levels: tuple[str, ...], resolver: EffectiveConfigResolver
) -> None:
    effective = await resolver.resolve(SQUAD)

    assert effective.source_of("models.investigator") is None


async def test_a_second_resolution_of_an_unchanged_hierarchy_is_served_from_cache(
    four_levels: tuple[str, ...], resolver: EffectiveConfigResolver
) -> None:
    first = await resolver.resolve(SQUAD)
    second = await resolver.resolve(SQUAD)

    assert second is first


async def test_changing_an_org_value_changes_every_descendants_next_resolution(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    """SC-006. The change is made at the root; every level below sees it."""
    await write_node(gateway, scope, PRIMARY_ORG, parent_id=None, settings={"budget": 8})
    before = {node_id: await resolver.resolve(node_id) for node_id in four_levels}
    assert all(config.value_at("budget") == 8 for config in before.values())

    await write_node(gateway, scope, PRIMARY_ORG, parent_id=None, settings={"budget": 3})

    for node_id in four_levels:
        after = await resolver.resolve(node_id)
        assert after.value_at("budget") == 3, node_id
        assert after is not before[node_id]


async def test_a_change_to_one_branch_does_not_invalidate_another(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    """A team's write must not cost every other team its cached resolution."""
    await write_node(gateway, scope, "team-search", parent_id=DIVISION)
    cached = await resolver.resolve(TEAM)

    await write_node(gateway, scope, "team-search", parent_id=DIVISION, settings={"budget": 1})

    assert await resolver.resolve(TEAM) is cached


async def test_a_change_at_the_node_itself_invalidates_it(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    await resolver.resolve(TEAM)

    await write_node(gateway, scope, TEAM, parent_id=DIVISION, settings={"budget": 2})

    assert (await resolver.resolve(TEAM)).value_at("budget") == 2


async def test_a_locked_ancestor_value_survives_resolution(
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
    resolver: EffectiveConfigResolver,
) -> None:
    """SC-002, through the whole read path rather than through merge alone."""
    await write_node(
        gateway,
        scope,
        PRIMARY_ORG,
        parent_id=None,
        settings={"policies": {"masking": {"level": "strict"}}},
        locked=("policies.masking.level",),
    )
    await write_node(
        gateway,
        scope,
        SQUAD,
        parent_id=TEAM,
        settings={"policies": {"masking": {"level": "off"}}},
    )

    effective = await resolver.resolve(SQUAD)

    assert effective.value_at("policies.masking.level") == "strict"
    assert effective.locked_by("policies.masking.level") == PRIMARY_ORG


async def test_the_cache_is_bounded(
    gateway: PersistenceGateway, scope: TenantScope, four_levels: tuple[str, ...]
) -> None:
    """Article II: an unbounded cache on a per-team key is a memory leak."""
    resolver = EffectiveConfigResolver(gateway=gateway, scope=scope, cache_size=2)

    for node_id in four_levels:
        await resolver.resolve(node_id)

    assert resolver.cached_entries == 2


async def test_resolving_an_unknown_node_says_which_one(
    four_levels: tuple[str, ...], resolver: EffectiveConfigResolver
) -> None:
    from platform.config_service.errors import UnknownNode

    with pytest.raises(UnknownNode, match="ghost"):
        await resolver.resolve("ghost")


async def test_one_organisation_cannot_resolve_another_s_node(
    gateway: PersistenceGateway,
    other_org_scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    resolver = EffectiveConfigResolver(gateway=gateway, scope=other_org_scope)

    from platform.config_service.errors import UnknownNode

    with pytest.raises(UnknownNode):
        await resolver.resolve(SQUAD)
