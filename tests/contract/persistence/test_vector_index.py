"""Contract: similarity search, dimension discipline, and re-embedding."""

from __future__ import annotations

import pytest

from config.constants.persistence import (
    EPISODE_VECTOR_NAMESPACE,
    MAX_INDEXABLE_EMBEDDING_DIMENSION,
    MAX_VECTOR_TOP_K,
)
from platform.persistence.errors import (
    BoundExceeded,
    EmbeddingDimensionMismatch,
    EmbeddingModelMismatch,
    GenerationNotFound,
    VectorNamespaceUnknown,
)
from platform.persistence.ports import (
    PersistenceGateway,
    TenantScope,
    UnitOfWork,
    VectorRecord,
)

pytestmark = pytest.mark.contract

MODEL = "bge-small-en-v1.5"


async def declare(uow: UnitOfWork, *, model: str = MODEL, dimension: int = 3) -> None:
    """Declare the episode namespace on ``uow``."""
    await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model=model, dimension=dimension)


def vector(vector_id: str, embedding: tuple[float, ...], **metadata: object) -> VectorRecord:
    """Return a vector record."""
    return VectorRecord(vector_id=vector_id, embedding=embedding, metadata=dict(metadata))


async def test_declaring_an_index_records_how_it_was_built(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # FR-013: tuning ``m`` upward and forgetting is the change that shows up
    # months later as "search got slower", with nothing to explain it.
    async with gateway.begin(scope) as uow:
        descriptor = await uow.vectors.ensure(
            EPISODE_VECTOR_NAMESPACE, model=MODEL, dimension=384, m=32
        )

    assert descriptor.model == MODEL
    assert descriptor.dimension == 384
    assert descriptor.m == 32
    assert descriptor.generation == 1


async def test_declaring_twice_with_the_same_shape_is_idempotent(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        first = await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model=MODEL, dimension=3)
        again = await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model=MODEL, dimension=3)

    assert first == again


async def test_redeclaring_with_a_different_shape_says_so(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)

        with pytest.raises(EmbeddingDimensionMismatch):
            await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model=MODEL, dimension=4)

        with pytest.raises(EmbeddingModelMismatch):
            await uow.vectors.ensure(
                EPISODE_VECTOR_NAMESPACE, model="a-different-model", dimension=3
            )


async def test_an_undeclared_namespace_is_not_created_by_writing_to_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An index that appeared on first write would have no recorded model, which
    # is the whole thing FR-012 exists to prevent.
    async with gateway.begin(scope) as uow:
        assert await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE) is None

        with pytest.raises(VectorNamespaceUnknown):
            await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector("v-1", (1.0, 0.0, 0.0))])


async def test_a_wrongly_shaped_embedding_fails_loudly_on_write(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """T045 / FR-012.

    Truncating or padding would not fail — it would return neighbours that are
    merely wrong, which nobody notices until retrieval has been bad for a month.
    """
    async with gateway.begin(scope) as uow:
        await declare(uow)

        with pytest.raises(EmbeddingDimensionMismatch) as failure:
            await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector("v-1", (1.0, 0.0))])

    assert failure.value.expected == 3
    assert failure.value.found == 2


async def test_a_wrongly_shaped_query_fails_too(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A query of the wrong shape returns neighbours as readily as a write of one
    # stores them.
    async with gateway.begin(scope) as uow:
        await declare(uow)

        with pytest.raises(EmbeddingDimensionMismatch):
            await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0))


async def test_a_batch_with_one_bad_vector_writes_none_of_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)

        with pytest.raises(EmbeddingDimensionMismatch):
            await uow.vectors.upsert(
                EPISODE_VECTOR_NAMESPACE,
                [vector("v-good", (1.0, 0.0, 0.0)), vector("v-bad", (1.0,))],
            )

        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 0


async def test_search_returns_the_nearest_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [
                vector("near", (1.0, 0.1, 0.0)),
                vector("far", (0.0, 0.0, 1.0)),
                vector("opposite", (-1.0, 0.0, 0.0)),
            ],
        )
        matches = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0, 0.0))

    assert [match.vector_id for match in matches] == ["near", "far", "opposite"]
    # Scores are similarities normalised to the unit interval, so larger is
    # nearer whatever distance operator the backend used underneath.
    assert 0.0 <= matches[-1].score < matches[0].score <= 1.0


async def test_metadata_filters_apply_by_equality_and_must_all_match(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [
                vector("prod", (1.0, 0.0, 0.0), environment="production", team="payments"),
                vector("staging", (1.0, 0.0, 0.0), environment="staging", team="payments"),
            ],
        )

        found = await uow.vectors.search(
            EPISODE_VECTOR_NAMESPACE,
            (1.0, 0.0, 0.0),
            filters={"environment": "production", "team": "payments"},
        )
        none = await uow.vectors.search(
            EPISODE_VECTOR_NAMESPACE,
            (1.0, 0.0, 0.0),
            filters={"environment": "production", "team": "search"},
        )

    assert [match.vector_id for match in found] == ["prod"]
    assert none == ()


async def test_top_k_is_honoured_and_bounded(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [vector(f"v-{n}", (1.0, float(n) / 10.0, 0.0)) for n in range(5)],
        )

        assert len(await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0, 0.0), k=2)) == 2

        with pytest.raises(BoundExceeded) as failure:
            await uow.vectors.search(
                EPISODE_VECTOR_NAMESPACE, (1.0, 0.0, 0.0), k=MAX_VECTOR_TOP_K + 1
            )

    assert failure.value.constant == "MAX_VECTOR_TOP_K"


async def test_an_index_wider_than_hnsw_supports_is_refused_at_declaration(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(BoundExceeded) as failure:
            await uow.vectors.ensure(
                EPISODE_VECTOR_NAMESPACE,
                model=MODEL,
                dimension=MAX_INDEXABLE_EMBEDDING_DIMENSION + 1,
            )

    assert failure.value.constant == "MAX_INDEXABLE_EMBEDDING_DIMENSION"


async def test_deleting_reaches_every_generation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An episode deleted for retention must not come back when a re-embed is
    # activated.
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector("v-1", (1.0, 0.0, 0.0))])
        second = await uow.vectors.begin_generation(
            EPISODE_VECTOR_NAMESPACE, model="new-model", dimension=2
        )
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE, [vector("v-1", (1.0, 0.0))], generation=second
        )

        assert await uow.vectors.delete(EPISODE_VECTOR_NAMESPACE, ["v-1"]) == 2


async def test_search_keeps_working_throughout_a_re_embed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-014: no window where search returns a half-migrated corpus."""
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector("old", (1.0, 0.0, 0.0))])

        # A new model with a different width — the case a plain write refuses.
        second = await uow.vectors.begin_generation(
            EPISODE_VECTOR_NAMESPACE, model="new-model", dimension=2
        )
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE, [vector("new", (1.0, 0.0))], generation=second
        )

        # Still answering from the old generation, in the old shape.
        during = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0, 0.0))
        assert [match.vector_id for match in during] == ["old"]

        descriptor = await uow.vectors.activate_generation(EPISODE_VECTOR_NAMESPACE, second)
        after = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0))

    assert descriptor.model == "new-model"
    assert descriptor.dimension == 2
    assert [match.vector_id for match in after] == ["new"]


async def test_the_active_generation_cannot_be_dropped(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An index with nothing in it answers every search with silence, and silence
    # is indistinguishable from "no similar incidents".
    async with gateway.begin(scope) as uow:
        await declare(uow)

        with pytest.raises(GenerationNotFound):
            await uow.vectors.drop_generation(EPISODE_VECTOR_NAMESPACE, 1)


async def test_a_superseded_generation_is_reclaimed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await declare(uow)
        await uow.vectors.upsert(EPISODE_VECTOR_NAMESPACE, [vector("old", (1.0, 0.0, 0.0))])
        second = await uow.vectors.begin_generation(
            EPISODE_VECTOR_NAMESPACE, model=MODEL, dimension=3
        )
        await uow.vectors.activate_generation(EPISODE_VECTOR_NAMESPACE, second)

        assert await uow.vectors.drop_generation(EPISODE_VECTOR_NAMESPACE, 1) == 1
