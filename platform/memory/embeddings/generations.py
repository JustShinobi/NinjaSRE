"""Declaring the episode index, and changing its model without search going down.

Two operations, and they are here together because they are two halves of one
fact: the index knows which model wrote it, so a write by a different model is
either a mistake or a migration and the system has to be told which.

``ensure_episode_index`` is the mistake half. It declares the namespace at the
embedder's model and width, and re-declaring it with different ones raises —
which is what turns "somebody changed the embedding model in configuration" from
a silent halving of recall quality into a startup failure with both model names
in it.

``reembed_episodes`` is the migration half. It opens a generation at the new
width, fills it in batches while search keeps reading the old one, verifies the
count, and swaps in one statement. The loop itself belongs to
``platform.persistence.reembedding`` — this module is what turns episodes into
vectors on the way through, which is the part that needs an embedder and
therefore cannot live down there.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from config.constants.memory import EMBEDDING_BATCH_SIZE
from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from platform.memory.embeddings.port import Embedder
from platform.memory.models import MemoryEpisode
from platform.persistence.errors import EmbeddingDimensionMismatch
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import IndexDescriptor, VectorRecord
from platform.persistence.reembedding import Reembedder, ReembedReport


@dataclass(frozen=True, slots=True)
class EmbeddingGeneration:
    """Which model wrote a generation of the episode index, and how wide it is."""

    model: str
    dimension: int
    generation: int

    @classmethod
    def of(cls, descriptor: IndexDescriptor) -> EmbeddingGeneration:
        """Return the generation an index descriptor describes."""
        return cls(
            model=descriptor.model,
            dimension=descriptor.dimension,
            generation=descriptor.generation,
        )


def verify_dimension(embedder: Embedder, embedding: Sequence[float]) -> tuple[float, ...]:
    """Return ``embedding`` if it matches the embedder's declared width, else raise.

    Loud, not silent, and raised before the write rather than by it. The index
    would catch this too, but by then the caller has already built a batch and
    the failure names a namespace rather than the model that produced the wrong
    shape.
    """
    if len(embedding) != embedder.dimension:
        raise EmbeddingDimensionMismatch(
            namespace=EPISODE_VECTOR_NAMESPACE,
            expected=embedder.dimension,
            found=len(embedding),
        )
    return tuple(embedding)


async def ensure_episode_index(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: Embedder,
) -> IndexDescriptor:
    """Declare the episode namespace at ``embedder``'s model and width.

    Idempotent while the model is unchanged. Raises ``EmbeddingModelMismatch`` or
    ``EmbeddingDimensionMismatch`` when it is not, because re-declaring an
    existing index with a different model is a re-embed and it has to say so.
    """
    async with gateway.begin(scope) as uow:
        return await uow.vectors.ensure(
            EPISODE_VECTOR_NAMESPACE,
            model=embedder.model,
            dimension=embedder.dimension,
        )


async def _vectors(
    episodes: AsyncIterator[Sequence[MemoryEpisode]],
    embedder: Embedder,
) -> AsyncIterator[Sequence[VectorRecord]]:
    """Yield each batch of episodes re-embedded, preserving the batching."""
    async for batch in episodes:
        if not batch:
            continue
        computed = await embedder.embed([episode.embedding_text() for episode in batch])
        yield [
            VectorRecord(
                vector_id=episode.correlation_id,
                embedding=verify_dimension(embedder, vector),
                metadata=episode.vector_metadata(),
            )
            for episode, vector in zip(batch, computed, strict=True)
        ]


async def reembed_episodes(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    embedder: Embedder,
    episodes: AsyncIterator[Sequence[MemoryEpisode]],
    expected: int | None = None,
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> ReembedReport:
    """Move the episode index onto ``embedder``, with search available throughout.

    ``episodes`` yields batches. Taking an iterator rather than reading the store
    here keeps the paging strategy with the caller — a corpus of a hundred
    thousand is read differently from one of a hundred, and neither way belongs
    to the embedder.

    ``expected`` is the corpus size the caller believes it is replacing. Given
    it, a generation that came up short raises and nothing is activated: a short
    generation activated is a search that silently returns fewer neighbours than
    it should, which is the failure this whole mechanism exists to avoid.
    """
    reembedder = Reembedder(gateway=gateway, scope=scope, batch_size=batch_size)
    return await reembedder.run(
        EPISODE_VECTOR_NAMESPACE,
        model=embedder.model,
        dimension=embedder.dimension,
        records=_vectors(episodes, embedder),
        expected=expected,
    )


__all__ = [
    "EmbeddingGeneration",
    "ensure_episode_index",
    "reembed_episodes",
    "verify_dimension",
]
