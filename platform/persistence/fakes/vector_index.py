"""In-memory vector storage and exact similarity search.

The search here is exhaustive rather than approximate, which is the one place
this fake is deliberately *better* than the backend it stands in for. HNSW is an
approximation, and a unit test that depended on which of two nearly-equidistant
neighbours came back would be a test that failed on an index rebuild. Exact
search makes the fake's answers a stable specification; recall of the real index
is measured by SC-002 against Postgres, where it belongs.

Everything else is held to the same rules the real index is: dimensions and
models are checked on every write *and every query*, generations exist and swap
atomically, and deletes reach every generation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.persistence import (
    DEFAULT_VECTOR_TOP_K,
    HNSW_EF_CONSTRUCTION,
    HNSW_EF_SEARCH,
    HNSW_M,
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
from platform.persistence.fakes.state import TenantState, VectorGeneration, VectorNamespace
from platform.persistence.ports.vector_index import (
    IndexDescriptor,
    SimilarityMatch,
    VectorRecord,
)


@dataclass(slots=True)
class FakeVectorIndex:
    """Vector namespaces for one organisation."""

    org_id: str
    state: TenantState

    async def ensure(
        self,
        namespace: str,
        *,
        model: str,
        dimension: int,
        m: int = HNSW_M,
        ef_construction: int = HNSW_EF_CONSTRUCTION,
        ef_search: int = HNSW_EF_SEARCH,
    ) -> IndexDescriptor:
        """Declare ``namespace`` if it does not exist, and return its descriptor."""
        if dimension > MAX_INDEXABLE_EMBEDDING_DIMENSION:
            raise BoundExceeded(
                parameter="dimension",
                requested=dimension,
                limit=MAX_INDEXABLE_EMBEDDING_DIMENSION,
                constant="MAX_INDEXABLE_EMBEDDING_DIMENSION",
            )
        if dimension < 1:
            raise ValueError(f"An index needs at least one dimension, got {dimension}.")

        existing = self.state.vector_indexes.get(namespace)
        if existing is not None:
            active = existing.active_generation
            if active.dimension != dimension:
                raise EmbeddingDimensionMismatch(
                    namespace=namespace, expected=active.dimension, found=dimension
                )
            if active.model != model:
                raise EmbeddingModelMismatch(
                    namespace=namespace, expected=active.model, found=model
                )
            return existing.descriptor()

        index = VectorNamespace(
            name=namespace,
            active=1,
            generations={1: VectorGeneration(number=1, model=model, dimension=dimension)},
            m=m,
            ef_construction=ef_construction,
            ef_search=ef_search,
            created_at=datetime.now(UTC),
        )
        self.state.vector_indexes[namespace] = index
        return index.descriptor()

    async def describe(self, namespace: str) -> IndexDescriptor | None:
        """Return the descriptor for ``namespace``, or ``None`` if undeclared."""
        index = self.state.vector_indexes.get(namespace)
        return index.descriptor() if index is not None else None

    async def upsert(
        self,
        namespace: str,
        records: Sequence[VectorRecord],
        *,
        generation: int | None = None,
    ) -> int:
        """Store ``records`` and return how many were written."""
        index = self._require_namespace(namespace)
        target = self._require_generation(index, generation)

        # Validated in full before anything is written. A partial batch would
        # leave the caller unable to tell which half landed.
        for record in records:
            if len(record.embedding) != target.dimension:
                raise EmbeddingDimensionMismatch(
                    namespace=namespace,
                    expected=target.dimension,
                    found=len(record.embedding),
                )

        for record in records:
            target.records[record.vector_id] = record
        return len(records)

    async def delete(self, namespace: str, vector_ids: Sequence[str]) -> int:
        """Delete the named vectors from every generation, and return the count."""
        index = self._require_namespace(namespace)
        removed = 0
        for generation in index.generations.values():
            for vector_id in vector_ids:
                if generation.records.pop(vector_id, None) is not None:
                    removed += 1
        return removed

    async def search(
        self,
        namespace: str,
        embedding: tuple[float, ...],
        *,
        k: int = DEFAULT_VECTOR_TOP_K,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[SimilarityMatch, ...]:
        """Return the ``k`` nearest neighbours in the active generation, best first."""
        if k > MAX_VECTOR_TOP_K:
            raise BoundExceeded(
                parameter="k", requested=k, limit=MAX_VECTOR_TOP_K, constant="MAX_VECTOR_TOP_K"
            )
        if k < 1:
            raise ValueError(f"A search must ask for at least one neighbour, got {k}.")

        index = self._require_namespace(namespace)
        generation = index.active_generation
        if len(embedding) != generation.dimension:
            raise EmbeddingDimensionMismatch(
                namespace=namespace, expected=generation.dimension, found=len(embedding)
            )

        matches = [
            SimilarityMatch(
                vector_id=record.vector_id,
                score=cosine_similarity(embedding, record.embedding),
                metadata=record.metadata,
            )
            for record in generation.records.values()
            if _matches(record.metadata, filters)
        ]
        matches.sort(key=lambda match: (-match.score, match.vector_id))
        return tuple(matches[:k])

    async def count(self, namespace: str, *, generation: int | None = None) -> int:
        """Return how many vectors a generation holds, active by default."""
        index = self._require_namespace(namespace)
        return len(self._require_generation(index, generation).records)

    async def begin_generation(
        self,
        namespace: str,
        *,
        model: str,
        dimension: int,
    ) -> int:
        """Open a new generation for re-embedding and return its number."""
        if dimension > MAX_INDEXABLE_EMBEDDING_DIMENSION:
            raise BoundExceeded(
                parameter="dimension",
                requested=dimension,
                limit=MAX_INDEXABLE_EMBEDDING_DIMENSION,
                constant="MAX_INDEXABLE_EMBEDDING_DIMENSION",
            )
        index = self._require_namespace(namespace)
        number = max(index.generations) + 1
        index.generations[number] = VectorGeneration(
            number=number, model=model, dimension=dimension
        )
        return number

    async def activate_generation(self, namespace: str, generation: int) -> IndexDescriptor:
        """Make ``generation`` the one searches read, and return the descriptor."""
        index = self._require_namespace(namespace)
        if generation not in index.generations:
            raise GenerationNotFound(namespace=namespace, generation=generation)
        index.active = generation
        return index.descriptor()

    async def drop_generation(self, namespace: str, generation: int) -> int:
        """Delete a non-active generation's vectors and return the count."""
        index = self._require_namespace(namespace)
        if generation not in index.generations or generation == index.active:
            raise GenerationNotFound(namespace=namespace, generation=generation)
        dropped = index.generations.pop(generation)
        return len(dropped.records)

    def _require_namespace(self, namespace: str) -> VectorNamespace:
        index = self.state.vector_indexes.get(namespace)
        if index is None:
            raise VectorNamespaceUnknown(namespace)
        return index

    @staticmethod
    def _require_generation(index: VectorNamespace, generation: int | None) -> VectorGeneration:
        if generation is None:
            return index.active_generation
        found = index.generations.get(generation)
        if found is None:
            raise GenerationNotFound(namespace=index.name, generation=generation)
        return found


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return the cosine similarity of two vectors, normalised to ``[0.0, 1.0]``.

    Cosine similarity runs from -1 to 1. Rescaling to the unit interval is what
    lets a caller treat the score as a confidence without knowing which distance
    operator the index was built with — and stops anybody sorting the wrong way
    round because they assumed a distance.

    A zero vector has no direction, so its similarity to anything is 0.0 rather
    than a division by zero.
    """
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return (dot / (left_norm * right_norm) + 1.0) / 2.0


def _matches(metadata: Mapping[str, Any], filters: Mapping[str, Any] | None) -> bool:
    """Return whether ``metadata`` satisfies every filter, by equality."""
    if not filters:
        return True
    return all(metadata.get(key) == value for key, value in filters.items())


__all__ = ["FakeVectorIndex", "cosine_similarity"]
