"""Contract: episodic memory."""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.ports import (
    Episode,
    EpisodeOutcome,
    PersistenceGateway,
    StoredStrategy,
    TenantScope,
)

pytestmark = pytest.mark.contract


def episode(
    episode_id: str,
    *,
    signature: str = "checkout-5xx",
    minutes: float = 0.0,
    outcome: EpisodeOutcome = EpisodeOutcome.RESOLVED,
    components: tuple[str, ...] = ("checkout",),
) -> Episode:
    """Return an episode at a fixed offset."""
    return Episode(
        episode_id=episode_id,
        title="Checkout 5xx spike",
        summary="Connection pool exhaustion under a retry storm.",
        signature=signature,
        outcome=outcome,
        run_id=f"run-{episode_id}",
        occurred_at=at(minutes),
        components=components,
        tags=("saturation",),
    )


async def test_an_episode_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-1"))
        found = await uow.episodes.get("ep-1")
        by_run = await uow.episodes.get_by_run("run-ep-1")

    assert found is not None
    assert by_run == found


async def test_the_same_fingerprint_recalls_prior_occurrences(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The exact-match half of recall. An alert that has fired before should be
    # recognised as such without depending on an embedding.
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-1", minutes=0))
        await uow.episodes.save(episode("ep-2", minutes=10))
        await uow.episodes.save(episode("ep-3", signature="database-failover"))

        found = await uow.episodes.by_signature("checkout-5xx")

    assert [item.episode_id for item in found] == ["ep-2", "ep-1"]


async def test_episodes_are_found_by_the_components_they_involved(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-1", components=("checkout", "postgres")))
        await uow.episodes.save(episode("ep-2", components=("search",)))

        found = await uow.episodes.by_component("postgres")

    assert [item.episode_id for item in found] == ["ep-1"]


async def test_inconclusive_episodes_are_kept_and_findable(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A corpus of successes only measures how well the system does on the
    # incidents it already handled.
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-1", outcome=EpisodeOutcome.RESOLVED))
        await uow.episodes.save(episode("ep-2", minutes=1, outcome=EpisodeOutcome.INCONCLUSIVE))

        found = await uow.episodes.list_recent(outcome=EpisodeOutcome.INCONCLUSIVE)
        assert [item.episode_id for item in found] == ["ep-2"]
        assert await uow.episodes.count() == 2


async def test_a_window_narrows_the_listing(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-old", minutes=0))
        await uow.episodes.save(episode("ep-new", minutes=60))

        found = await uow.episodes.list_recent(since=at(30))

    assert [item.episode_id for item in found] == ["ep-new"]


async def test_deleting_reports_whether_it_was_there(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("ep-1"))

        assert await uow.episodes.delete("ep-1") is True
        assert await uow.episodes.delete("ep-1") is False


# -- synthesised strategies ----------------------------------------------------


def strategy(
    *,
    team_node_id: str = "team-checkout",
    issue_type: str = "connection_pool_exhaustion",
    component_key: str = "service:checkout",
    minutes: float = 0.0,
    stale: bool = False,
) -> StoredStrategy:
    """Return a playbook at a fixed offset."""
    return StoredStrategy(
        team_node_id=team_node_id,
        issue_type=issue_type,
        component_key=component_key,
        content={"common_root_causes": ["a retry storm exhausting the pool"], "episode_count": 4},
        generated_at=at(minutes),
        stale=stale,
    )


async def test_a_strategy_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy())
        found = await uow.episodes.get_strategy(
            team_node_id="team-checkout",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
        )

    assert found is not None
    assert found.content["episode_count"] == 4
    assert found.generated_at == at(0)
    assert found.stale is False


async def test_saving_the_same_key_replaces_rather_than_duplicates(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # This is what makes two concurrent syntheses converge on one row rather
    # than on two playbooks for the same subject.
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy())
        await uow.episodes.save_strategy(strategy(minutes=60))

        listed = await uow.episodes.list_strategies(team_node_id="team-checkout")

    assert len(listed) == 1
    assert listed[0].generated_at == at(60)


async def test_a_missing_strategy_is_none(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        found = await uow.episodes.get_strategy(
            team_node_id="team-checkout", issue_type="nothing", component_key="service:nothing"
        )

    assert found is None


async def test_marking_stale_reports_only_what_changed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy())

        first = await uow.episodes.mark_strategies_stale(
            team_node_id="team-checkout",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
        )
        second = await uow.episodes.mark_strategies_stale(
            team_node_id="team-checkout",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
        )
        missing = await uow.episodes.mark_strategies_stale(
            team_node_id="team-checkout", issue_type="nothing", component_key="service:nothing"
        )
        found = await uow.episodes.get_strategy(
            team_node_id="team-checkout",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
        )

    assert (first, second, missing) == (1, 0, 0)
    assert found is not None
    assert found.stale is True


async def test_a_stale_strategy_is_still_returned(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Marked, never hidden: the reader is the only party that knows whether it
    # can afford to regenerate.
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy(stale=True))
        found = await uow.episodes.get_strategy(
            team_node_id="team-checkout",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
        )

    assert found is not None
    assert found.stale is True


async def test_strategies_list_newest_first_within_one_team(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy(issue_type="old", minutes=0))
        await uow.episodes.save_strategy(strategy(issue_type="new", minutes=60))
        await uow.episodes.save_strategy(strategy(team_node_id="team-search", issue_type="theirs"))

        listed = await uow.episodes.list_strategies(team_node_id="team-checkout")

    assert [item.issue_type for item in listed] == ["new", "old"]


async def test_the_component_type_keeps_two_subjects_apart(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy(component_key="service:checkout"))
        await uow.episodes.save_strategy(strategy(component_key="database:checkout"))

        listed = await uow.episodes.list_strategies(team_node_id="team-checkout")

    assert len(listed) == 2


async def test_deleting_a_strategy_reports_whether_it_was_there(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.episodes.save_strategy(strategy())
        key = {
            "team_node_id": "team-checkout",
            "issue_type": "connection_pool_exhaustion",
            "component_key": "service:checkout",
        }

        assert await uow.episodes.delete_strategy(**key) is True
        assert await uow.episodes.delete_strategy(**key) is False
