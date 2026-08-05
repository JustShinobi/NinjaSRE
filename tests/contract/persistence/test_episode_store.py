"""Contract: episodic memory."""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.ports import (
    Episode,
    EpisodeOutcome,
    PersistenceGateway,
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
