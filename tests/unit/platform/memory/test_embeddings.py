"""The default embedder, the width check, and a model change with search still up.

SC-007 is the first claim here: a deployment that may not egress keeps full
memory function. That is asserted the only way it can be — the default embedder
is exercised end to end, and nothing it does can reach a network, because it is
arithmetic over a string.

SC-008 is the second: re-embedding a corpus leaves search available throughout
and switches atomically. The corpus here is a few hundred rather than a hundred
thousand, because the property being asserted is *generational* rather than
*scalar* — the hundred-thousand claim is measured against a real PostgreSQL in
the persistence scale suite, where an approximate index actually exists to be
slow. What this proves is that at no point during the swap does a search see a
half-migrated corpus.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from platform.memory.embeddings.generations import (
    EmbeddingGeneration,
    ensure_episode_index,
    reembed_episodes,
    verify_dimension,
)
from platform.memory.embeddings.local import LocalEmbedder, tokenise
from platform.memory.embeddings.port import embed_one
from platform.memory.embeddings.provider import ProviderEmbedder
from platform.memory.models import Component, MemoryEpisode
from platform.persistence.errors import EmbeddingDimensionMismatch, EmbeddingModelMismatch
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.reembedding import ReembedIncomplete
from tests.unit.platform.memory.conftest import PAYMENTS_TEAM, PRIMARY_ORG, at

pytestmark = pytest.mark.unit

#: Enough episodes that a re-embed runs several batches, and few enough that the
#: suite stays a unit suite. The generation swap is what is under test, and it
#: behaves identically at a hundred thousand and at four.
CORPUS = 800


def corpus_episode(index: int, *, resolved: bool = True) -> MemoryEpisode:
    """Return one episode of a synthetic corpus."""
    return MemoryEpisode(
        correlation_id=f"conv-{index}",
        org_id=PRIMARY_ORG,
        team_node_id=PAYMENTS_TEAM,
        issue_type="oom_kill" if index % 2 else "certificate_expiry",
        issue_description=f"service-{index} failed at 0{index % 10}:00",
        components=(Component(type="service", name=f"service-{index}"),),
        resolved=resolved,
        root_cause=f"cause number {index}",
        summary=f"An investigation into service-{index}.",
        occurred_at=at(-index / 100),
    )


async def batched(
    episodes: Sequence[MemoryEpisode], size: int
) -> AsyncIterator[Sequence[MemoryEpisode]]:
    """Yield ``episodes`` in batches, as a re-embedding source would."""
    for start in range(0, len(episodes), size):
        yield episodes[start : start + size]


class WideBackend:
    """A hosted model that returns vectors of a width it did not declare."""

    def __init__(self, width: int) -> None:
        self.width = width

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input, at this backend's actual width."""
        return [[0.5] * self.width for _ in texts]


class DroppingBackend:
    """A hosted model that silently returns fewer vectors than it was asked for."""

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector fewer than asked."""
        return [[1.0, 0.0] for _ in texts][:-1]


# -- the local model ----------------------------------------------------------


async def test_the_local_embedder_is_deterministic_across_calls() -> None:
    """A vector stored today has to still mean the same thing tomorrow.

    Python's ``hash`` is salted per process, so a lexical embedder built on it
    would produce a corpus one worker could write and the next could not search.
    """
    embedder = LocalEmbedder()

    first = await embed_one(embedder, "payments-api OOMKilled exit code 137")
    second = await embed_one(embedder, "payments-api OOMKilled exit code 137")

    assert first == second
    assert len(first) == embedder.dimension


async def test_the_local_embedder_ranks_the_same_failure_above_a_different_one() -> None:
    """SC-007: a no-egress deployment gets recall that is useful, not merely present."""
    from platform.persistence.fakes.vector_index import cosine_similarity

    embedder = LocalEmbedder()
    query = await embed_one(embedder, "payments-api OOMKilled exit code 137")
    same = await embed_one(embedder, "payments-api pod OOMKilled with exit code 137 again")
    other = await embed_one(embedder, "search-api certificate expired for the ingress")

    assert cosine_similarity(query, same) > cosine_similarity(query, other)


async def test_empty_text_embeds_to_a_zero_vector_rather_than_failing() -> None:
    """An episode with nothing extractable is still writable; it just matches nothing."""
    vector = await embed_one(LocalEmbedder(), "")

    assert set(vector) == {0.0}


def test_identifiers_survive_tokenisation_whole() -> None:
    """Splitting ``payments-api`` in two would match half the estate."""
    assert tokenise("payments-api restarted; node-7.local") == (
        "payments-api",
        "restarted",
        "node-7.local",
    )


# -- the width check ----------------------------------------------------------


def test_a_wrong_width_fails_loudly_before_the_write() -> None:
    """A vector of the wrong shape would be padded, truncated, or indexed — all silent."""
    embedder = LocalEmbedder()

    with pytest.raises(EmbeddingDimensionMismatch):
        verify_dimension(embedder, (0.1, 0.2, 0.3))


async def test_a_provider_that_changed_width_is_refused() -> None:
    """A hosted model that shipped a new version must not half-fill a corpus."""
    embedder = ProviderEmbedder(backend=WideBackend(width=7), model="hosted-v2", dimension=4)

    with pytest.raises(EmbeddingDimensionMismatch):
        await embedder.embed(["anything"])


async def test_a_provider_that_dropped_an_input_is_refused() -> None:
    """Zipping vectors against the wrong episodes produces confident nonsense."""
    embedder = ProviderEmbedder(backend=DroppingBackend(), model="hosted", dimension=2)

    with pytest.raises(ValueError, match="one vector per input"):
        await embedder.embed(["one", "two"])


async def test_redeclaring_the_index_with_another_model_is_a_migration_not_a_write(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-018: changing the model in configuration fails at startup, with both names."""
    await ensure_episode_index(gateway, scope, LocalEmbedder())

    with pytest.raises(EmbeddingModelMismatch):
        await ensure_episode_index(
            gateway, scope, LocalEmbedder(model="other-model", dimension=256)
        )


async def test_declaring_the_index_twice_with_the_same_model_is_idempotent(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Every process start declares the namespace; only the first one creates it."""
    first = await ensure_episode_index(gateway, scope, LocalEmbedder())
    second = await ensure_episode_index(gateway, scope, LocalEmbedder())

    assert EmbeddingGeneration.of(first) == EmbeddingGeneration.of(second)


# -- re-embedding -------------------------------------------------------------


async def test_reembedding_keeps_search_available_and_swaps_atomically(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-008: the corpus changes model with no window in which search is wrong.

    Search is exercised before the pass, part-way through it, and after — and the
    part-way search is the one that matters. It has to return neighbours of the
    *old* width from the *old* generation, because the new one is still filling.
    """
    old = LocalEmbedder(model="local-v1", dimension=64)
    new = LocalEmbedder(model="local-v2", dimension=128)
    episodes = [corpus_episode(index) for index in range(CORPUS)]

    await ensure_episode_index(gateway, scope, old)
    async with gateway.begin(scope) as uow:
        for episode in episodes:
            await uow.episodes.save(episode.to_stored())
    await reembed_episodes(
        gateway, scope, embedder=old, episodes=batched(episodes, 200), expected=CORPUS
    )

    before = await search(gateway, scope, old, "service-7 failed")
    assert before, "search must work before the migration"

    observed: list[int] = []

    async def watched() -> AsyncIterator[Sequence[MemoryEpisode]]:
        """Yield batches, searching between each one."""
        async for batch in batched(episodes, 200):
            observed.append(len(await search(gateway, scope, old, "service-7 failed")))
            yield batch

    report = await reembed_episodes(
        gateway, scope, embedder=new, episodes=watched(), expected=CORPUS
    )

    assert report.written == CORPUS
    assert all(count > 0 for count in observed), "search went down during the migration"
    assert await search(gateway, scope, new, "service-7 failed")

    async with gateway.begin(scope) as uow:
        descriptor = await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE)
    assert descriptor is not None
    assert (descriptor.model, descriptor.dimension) == ("local-v2", 128)


async def test_a_short_generation_is_not_activated(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A generation missing rows would be a search that silently returns fewer."""
    old = LocalEmbedder(model="local-v1", dimension=64)
    episodes = [corpus_episode(index) for index in range(10)]

    await ensure_episode_index(gateway, scope, old)
    await reembed_episodes(gateway, scope, embedder=old, episodes=batched(episodes, 5))

    with pytest.raises(ReembedIncomplete):
        await reembed_episodes(
            gateway,
            scope,
            embedder=LocalEmbedder(model="local-v2", dimension=128),
            episodes=batched(episodes[:3], 5),
            expected=10,
        )

    async with gateway.begin(scope) as uow:
        descriptor = await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE)
    assert descriptor is not None
    assert descriptor.model == "local-v1", "the old generation must still be serving"


async def search(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    text: str,
) -> tuple[object, ...]:
    """Return the neighbours of ``text`` under whichever generation is active."""
    embedding = await embed_one(embedder, text)
    async with gateway.begin(scope) as uow:
        try:
            return await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, embedding, k=5)
        except EmbeddingDimensionMismatch:
            # The active generation is a different width than this embedder, which
            # is a failed migration rather than an empty result — surface it.
            raise
