"""Contract: a corpus changes embedding model without search going down (FR-014)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from platform.persistence.errors import GenerationNotFound
from platform.persistence.ports import PersistenceGateway, TenantScope, VectorRecord
from platform.persistence.reembedding import Reembedder, ReembedIncomplete

pytestmark = pytest.mark.contract

OLD_MODEL = "bge-small-en-v1.5"
NEW_MODEL = "bge-base-en-v1.5"


async def batches(
    *groups: Sequence[VectorRecord],
) -> AsyncIterator[Sequence[VectorRecord]]:
    """Yield each group in turn, as a re-embedding source would."""
    for group in groups:
        yield group


def wide(vector_id: str, first: float) -> VectorRecord:
    """Return a four-dimensional record, as the new model produces."""
    return VectorRecord(vector_id=vector_id, embedding=(first, 0.0, 0.0, 1.0))


async def seed_old_generation(gateway: PersistenceGateway, scope: TenantScope) -> None:
    """Declare the namespace at the old model's width and fill it."""
    async with gateway.begin(scope) as uow:
        await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model=OLD_MODEL, dimension=2)
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [
                VectorRecord(vector_id="ep-1", embedding=(1.0, 0.0)),
                VectorRecord(vector_id="ep-2", embedding=(0.0, 1.0)),
            ],
        )


async def test_a_corpus_moves_to_a_wider_model_and_the_old_one_is_reclaimed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await seed_old_generation(gateway, scope)

    report = await Reembedder(gateway, scope).run(
        EPISODE_VECTOR_NAMESPACE,
        model=NEW_MODEL,
        dimension=4,
        records=batches([wide("ep-1", 1.0), wide("ep-2", 0.5)]),
        expected=2,
    )

    assert report.written == 2
    assert report.dropped == 2
    assert report.descriptor is not None
    assert report.descriptor.model == NEW_MODEL
    assert report.descriptor.dimension == 4

    async with gateway.begin(scope) as uow:
        # Searching in the new width works; the old generation is gone.
        matches = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0, 0.0, 1.0), k=2)
        assert [match.vector_id for match in matches] == ["ep-1", "ep-2"]

        with pytest.raises(GenerationNotFound):
            await uow.vectors.count(EPISODE_VECTOR_NAMESPACE, generation=report.generation - 1)


async def test_search_keeps_answering_from_the_old_model_until_the_swap(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The whole point of FR-014.

    Half-way through a re-embed, a search must still return the old
    generation's answers in the old width — not an error, and not a half-built
    corpus.
    """
    await seed_old_generation(gateway, scope)

    async with gateway.begin(scope) as uow:
        generation = await uow.vectors.begin_generation(
            EPISODE_VECTOR_NAMESPACE, model=NEW_MODEL, dimension=4
        )
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE, [wide("ep-1", 1.0)], generation=generation
        )

    async with gateway.begin(scope) as uow:
        during = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0))
        assert {match.vector_id for match in during} == {"ep-1", "ep-2"}

        descriptor = await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE)
        assert descriptor is not None
        assert descriptor.model == OLD_MODEL


async def test_a_short_generation_is_not_activated(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A corpus with holes in it would return fewer neighbours and say nothing."""
    await seed_old_generation(gateway, scope)

    with pytest.raises(ReembedIncomplete) as failure:
        await Reembedder(gateway, scope).run(
            EPISODE_VECTOR_NAMESPACE,
            model=NEW_MODEL,
            dimension=4,
            records=batches([wide("ep-1", 1.0)]),
            expected=2,
        )

    assert failure.value.written == 1
    assert failure.value.expected == 2

    async with gateway.begin(scope) as uow:
        # Still the old model, still answering, still complete.
        descriptor = await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE)
        assert descriptor is not None
        assert descriptor.model == OLD_MODEL
        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 2


async def test_batches_are_written_in_their_own_units_of_work(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A pass that dies half way has written half a generation nobody is reading."""
    await seed_old_generation(gateway, scope)

    report = await Reembedder(gateway, scope, batch_size=1).run(
        EPISODE_VECTOR_NAMESPACE,
        model=NEW_MODEL,
        dimension=4,
        records=batches([wide("ep-1", 1.0), wide("ep-2", 0.5)], [wide("ep-3", 0.25)]),
        expected=3,
    )

    assert report.written == 3
    async with gateway.begin(scope) as uow:
        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 3
