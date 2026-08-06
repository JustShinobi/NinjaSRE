"""Retention: an episode and its vector leave together, or the index rots.

The failure this file exists to prevent is quiet. A vector whose episode has been
deleted is a neighbour every search keeps returning and every retrieval keeps
failing to load, which reads as a corpus that is mysteriously shrinking rather
than as a deletion that half happened.
"""

from __future__ import annotations

import pytest

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE, RETENTION_DAYS_EPISODES
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.purge import purge_episodes, purge_expired, retention_cutoff
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.memory.conftest import at
from tests.unit.platform.memory.test_retrieval_and_ranking import episode, seed

pytestmark = pytest.mark.unit


async def counts(gateway: PersistenceGateway, scope: TenantScope) -> tuple[int, int]:
    """Return how many episodes and how many vectors this team holds."""
    async with gateway.begin(scope) as uow:
        return await uow.episodes.count(), await uow.vectors.count(EPISODE_VECTOR_NAMESPACE)


async def test_purging_an_episode_takes_its_vector_with_it(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """One unit of work, both stores. Anything else leaves the index rotting."""
    await seed(gateway, scope, embedder, episode("keep", scope), episode("drop", scope))

    report = await purge_episodes(gateway, scope, ["drop"])

    assert (report.episodes, report.vectors) == (1, 1)
    assert await counts(gateway, scope) == (1, 1)


async def test_purging_nothing_touches_nothing(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """An empty request is a no-op rather than a full sweep."""
    await seed(gateway, scope, embedder, episode("keep", scope))

    report = await purge_episodes(gateway, scope, [])

    assert report.episodes == 0
    assert await counts(gateway, scope) == (1, 1)


async def test_purging_before_anything_was_indexed_still_deletes_the_episodes(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A tenant with episodes and no index is odd, and the deletion still has to work."""
    async with gateway.begin(scope) as uow:
        await uow.episodes.save(episode("orphan", scope).to_stored())

    report = await purge_episodes(gateway, scope, ["orphan"])

    assert report.episodes == 1
    assert report.vectors == 0


async def test_expired_episodes_are_swept_and_recent_ones_are_not(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The retention window is honoured on both sides of the cutoff."""
    await seed(
        gateway,
        scope,
        embedder,
        episode("recent", scope, age_days=10),
        episode("ancient", scope, age_days=RETENTION_DAYS_EPISODES + 30),
    )

    report = await purge_expired(gateway, scope, now=at())

    assert report.episodes == 1
    assert await counts(gateway, scope) == (1, 1)


def test_the_retention_window_defaults_to_the_platform_constant() -> None:
    """Episodes outlive traces on purpose — the corpus is what ablation measures."""
    cutoff = retention_cutoff(now=at())

    assert (at() - cutoff).days == RETENTION_DAYS_EPISODES


def test_a_window_of_less_than_a_day_is_refused() -> None:
    """A misconfigured window that deleted everything would be a silent data loss."""
    with pytest.raises(ValueError, match="at least a day"):
        retention_cutoff(days=0)
