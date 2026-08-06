"""The cache is a cache, and it is invalidated by facts rather than by guesses.

Three claims, all of them counting arguments against a real store rather than a
mock, and each fails in a different way if the counting is skipped:

- **A cache hit costs nothing.** A cache that returns the right answer while still
  calling the model is a cache that costs what it was built to save, and nothing
  but a call counter says so.
- **An episode write invalidates.** An invalidation that is not asserted end to end
  is an invalidation that keys the write side differently from the read side,
  which produces a playbook that is merely out of date and therefore looks fine.
- **Concurrent requests generate once.** A lock is only observable under
  contention, so the double is made to suspend inside the call. Without that, the
  first caller finishes before the second starts and the test passes against no
  lock at all.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from config.constants.memory import STRATEGY_MAX_AGE_DAYS
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.models import MemoryEpisode
from platform.memory.strategy.cache import StrategyCache
from platform.memory.strategy.invalidation import StrategyInvalidator, invalidation_keys
from platform.memory.strategy.models import StrategyKey
from platform.memory.strategy.policy import StrategyPolicy
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.memory.conftest import at
from tests.unit.platform.memory.strategy.conftest import (
    CountingLLM,
    cache_for,
    episode,
    key_for,
    mixed_corpus,
    scored,
)

pytestmark = pytest.mark.unit


async def invalidate(
    gateway: PersistenceGateway, scope: TenantScope, written: MemoryEpisode
) -> int:
    """Invalidate as the episode write hook does, in its own unit of work."""
    async with gateway.begin(scope) as uow:
        return await StrategyInvalidator().on_episode_written(uow, written)


# -- a cache hit costs nothing ------------------------------------------------


async def test_a_cache_hit_performs_no_model_call(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    cache = cache_for(gateway, scope, synthesis_llm)
    episodes = scored(*mixed_corpus(scope))
    key = key_for(scope)

    first = await cache.get_or_generate(key, episodes)
    assert first.generated
    assert synthesis_llm.call_count == 1

    second = await cache.get_or_generate(key, episodes)

    assert second.cached
    assert not second.generated
    assert synthesis_llm.call_count == 1, "the second request synthesised again"
    assert second.strategy is not None
    assert second.strategy.root_causes == first.strategy.root_causes  # type: ignore[union-attr]


async def test_reading_never_generates(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """``get`` is the console's path, and a console must not spend model calls."""
    cache = cache_for(gateway, scope, synthesis_llm)

    lookup = await cache.get(key_for(scope))

    assert lookup.strategy is None
    assert synthesis_llm.call_count == 0


# -- an episode write invalidates the playbook it bears on -------------------


async def test_writing_a_matching_episode_invalidates_and_the_next_request_regenerates(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    cache = cache_for(gateway, scope, synthesis_llm)
    episodes = scored(*mixed_corpus(scope))
    key = key_for(scope)

    await cache.get_or_generate(key, episodes)
    assert synthesis_llm.call_count == 1

    # A sixth investigation of the same failure, on a naming variant of the same
    # component — which is the case normalisation exists for.
    changed = await invalidate(
        gateway, scope, episode("ep-6", scope, components=("service:payments-service",))
    )
    assert changed == 1

    regenerated = await cache.get_or_generate(key, episodes)

    assert regenerated.generated
    assert synthesis_llm.call_count == 2


async def test_an_unrelated_episode_invalidates_nothing(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """Over-eager invalidation would make the cache a cache of nothing."""
    cache = cache_for(gateway, scope, synthesis_llm)
    await cache.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    other_failure = await invalidate(
        gateway, scope, episode("ep-other", scope, issue_type="certificate_expiry")
    )
    other_component = await invalidate(
        gateway, scope, episode("ep-elsewhere", scope, components=("service:search",))
    )

    assert other_failure == 0
    assert other_component == 0
    assert (await cache.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))).cached
    assert synthesis_llm.call_count == 1


async def test_invalidating_an_already_stale_playbook_reports_no_change(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """ "Invalidated 1" on every write would make the signal meaningless."""
    cache = cache_for(gateway, scope, synthesis_llm)
    await cache.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    first = await invalidate(gateway, scope, episode("ep-6", scope))
    second = await invalidate(gateway, scope, episode("ep-7", scope))

    assert first == 1
    assert second == 0


async def test_an_unclassified_episode_invalidates_nothing(scope: TenantScope) -> None:
    """Synthesis keys on the pair, so an episode with no issue type belongs to none."""
    assert invalidation_keys(episode("ep-x", scope, issue_type="")) == ()


async def test_the_write_side_and_the_read_side_agree_on_the_key(scope: TenantScope) -> None:
    """The symmetry the whole mechanism rests on, asserted directly."""
    written = episode("ep-1", scope, components=("service:payments-7f9dd8b6c4-x7gr9",))

    assert key_for(scope).component_key in invalidation_keys(written)


# -- age forces regeneration on its own ---------------------------------------


async def test_a_playbook_older_than_the_ceiling_regenerates(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    cache = cache_for(gateway, scope, synthesis_llm)
    episodes = scored(*mixed_corpus(scope))
    key = key_for(scope)

    await cache.get_or_generate(key, episodes)
    assert synthesis_llm.call_count == 1

    # The same cache, a month later. Nothing invalidated it; it is simply old
    # enough that nobody has confirmed it describes the infrastructure any more.
    later = StrategyCache(
        gateway=gateway,
        scope=scope,
        generator=cache.generator,
        policy=cache.policy,
        clock=lambda: at(STRATEGY_MAX_AGE_DAYS + 1),
    )
    outcome = await later.get_or_generate(key, episodes)

    assert outcome.generated
    assert synthesis_llm.call_count == 2


async def test_a_playbook_inside_the_ceiling_is_served(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    cache = cache_for(gateway, scope, synthesis_llm)
    episodes = scored(*mixed_corpus(scope))
    await cache.get_or_generate(key_for(scope), episodes)

    almost = StrategyCache(
        gateway=gateway,
        scope=scope,
        generator=cache.generator,
        policy=cache.policy,
        clock=lambda: at(STRATEGY_MAX_AGE_DAYS - 1),
    )

    assert (await almost.get_or_generate(key_for(scope), episodes)).cached
    assert synthesis_llm.call_count == 1


# -- concurrent requests produce one generation -------------------------------


async def test_concurrent_requests_for_one_key_generate_once(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """An alert storm is N investigations of one component arriving together."""
    from tests.unit.platform.memory.strategy.conftest import SYNTHESIS_REPLY

    llm = CountingLLM(structured=dict(SYNTHESIS_REPLY), delay=0.02)
    cache = cache_for(gateway, scope, llm)
    episodes = scored(*mixed_corpus(scope))
    key = key_for(scope)

    results = await asyncio.gather(*(cache.get_or_generate(key, episodes) for _ in range(8)))

    assert llm.call_count == 1, f"{llm.call_count} syntheses for one key"
    assert all(found.strategy is not None for found in results)
    assert sum(1 for found in results if found.generated) == 1
    # And the seven that waited got the winner's playbook, not a different one.
    assert len({found.strategy.root_causes for found in results if found.strategy}) == 1


async def test_concurrent_requests_for_different_keys_are_not_serialised(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The lock is per key; two unrelated failures must not queue behind each other."""
    from tests.unit.platform.memory.strategy.conftest import SYNTHESIS_REPLY

    llm = CountingLLM(structured=dict(SYNTHESIS_REPLY), delay=0.02)
    cache = cache_for(gateway, scope, llm)
    episodes = scored(*mixed_corpus(scope))

    await asyncio.gather(
        cache.get_or_generate(key_for(scope, issue_type="oom_kill"), episodes),
        cache.get_or_generate(key_for(scope, issue_type="certificate_expiry"), episodes),
    )

    assert llm.call_count == 2


async def test_the_lock_table_does_not_grow_without_bound(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """A deployment that has synthesised ten thousand keys holds no locks at rest."""
    cache = cache_for(gateway, scope, synthesis_llm)
    episodes = scored(*mixed_corpus(scope))

    for index in range(5):
        await cache.get_or_generate(key_for(scope, issue_type=f"failure_{index}"), episodes)

    assert cache.locks._locks == {}
    assert cache.locks._waiters == {}


# -- scoping ------------------------------------------------------------------


async def test_one_team_cannot_read_another_teams_playbook(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    synthesis_llm: CountingLLM,
) -> None:
    mine = cache_for(gateway, scope, synthesis_llm)
    await mine.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    theirs = cache_for(gateway, other_team_scope, synthesis_llm)
    lookup = await theirs.get(key_for(other_team_scope))

    assert lookup.strategy is None


async def test_one_organisation_cannot_read_anothers_playbook(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_org_scope: TenantScope,
    synthesis_llm: CountingLLM,
) -> None:
    mine = cache_for(gateway, scope, synthesis_llm)
    await mine.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    theirs = cache_for(gateway, other_org_scope, synthesis_llm)

    assert (await theirs.get(key_for(other_org_scope))).strategy is None


async def test_a_key_from_another_tenant_is_refused_rather_than_narrowed(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    synthesis_llm: CountingLLM,
) -> None:
    """Silently rewriting the key would answer a question nobody asked."""
    cache = cache_for(gateway, scope, synthesis_llm)

    with pytest.raises(ValueError, match="scoped to"):
        await cache.get(key_for(other_team_scope))


async def test_an_episode_write_invalidates_only_its_own_teams_playbook(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    synthesis_llm: CountingLLM,
) -> None:
    mine = cache_for(gateway, scope, synthesis_llm)
    theirs = cache_for(gateway, other_team_scope, synthesis_llm)
    await mine.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))
    await theirs.get_or_generate(key_for(other_team_scope), scored(*mixed_corpus(other_team_scope)))
    assert synthesis_llm.call_count == 2

    await invalidate(gateway, other_team_scope, episode("ep-theirs", other_team_scope))

    assert (await mine.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))).cached
    assert synthesis_llm.call_count == 2


# -- ablation ------------------------------------------------------------------


async def test_the_switch_disables_generation_and_retrieval_together(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """A run that could retrieve but not generate would report an accident."""
    enabled = cache_for(gateway, scope, synthesis_llm)
    await enabled.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))
    assert synthesis_llm.call_count == 1

    off = cache_for(gateway, scope, synthesis_llm, policy=StrategyPolicy.disabled())

    assert (await off.get(key_for(scope))).strategy is None
    assert (
        await off.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))
    ).strategy is None
    assert synthesis_llm.call_count == 1


# -- degradation ---------------------------------------------------------------


async def test_a_failed_regeneration_serves_the_stale_playbook(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A provider outage must not take the old answer away as well as the new one."""
    from tests.unit.platform.memory.strategy.conftest import SYNTHESIS_REPLY

    llm = CountingLLM(structured=dict(SYNTHESIS_REPLY))
    cache = cache_for(gateway, scope, llm)
    episodes = scored(*mixed_corpus(scope))
    await cache.get_or_generate(key_for(scope), episodes)

    await invalidate(gateway, scope, episode("ep-6", scope))
    llm.structured = None  # the provider stops returning anything usable

    outcome = await cache.get_or_generate(key_for(scope), episodes)

    assert outcome.strategy is not None
    assert outcome.strategy.stale
    assert outcome.reason


async def test_a_key_with_no_playbook_and_a_broken_provider_returns_nothing_and_says_why(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    cache = cache_for(gateway, scope, CountingLLM(structured=None))

    outcome = await cache.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    assert outcome.strategy is None
    assert outcome.reason


def test_a_key_needs_both_halves(scope: TenantScope) -> None:
    """A playbook for "anything on anything" generalises over unrelated episodes."""
    with pytest.raises(ValueError, match="issue type and a component key"):
        StrategyKey(
            org_id=scope.org_id,
            team_node_id=scope.team_node_id or "",
            issue_type="",
            component_key="service:payments",
        )


def test_the_age_check_treats_an_undated_playbook_as_expired(
    scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """Degrading to the conservative answer, rather than serving it forever."""
    from platform.memory.strategy.models import Strategy

    undated = Strategy(key=key_for(scope), root_causes=("something",))

    assert undated.expired(at())
    assert not undated.fresh(at())
    assert undated.age_days(at() + timedelta(days=1)) == float("inf")
