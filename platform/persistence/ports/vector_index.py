"""Similarity search, with the embedding model written down beside every vector.

Two decisions shape this port, and both come from the same observation: a vector
store fails silently or not at all.

**Dimension and model are recorded, and a mismatch is an error** (FR-012). An
embedding of the wrong width could be truncated, padded, or written into a
differently-shaped index, and all three of those *return results*. They are
merely the wrong results, and nothing downstream can tell. So an index declares
its model and dimension once, at ``ensure``, and every write is checked against
that declaration.

**Changing the embedding model is a generation, not a write** (FR-014). The
corpus has to be re-embedded, which takes hours on a real deployment, and search
has to keep working throughout. ``begin_generation`` opens a second, invisible
population that writes land in; ``activate_generation`` swaps which one searches
read, in one statement; ``drop_generation`` reclaims the old one afterwards. At
no point is there a window where search returns a half-migrated corpus.

Scores are similarities, not distances: higher is better, and cosine
similarities are normalised to ``[0.0, 1.0]``. The alternative is every caller
knowing which operator the index was built with, and one of them eventually
sorting the wrong way round.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.persistence import (
    DEFAULT_VECTOR_TOP_K,
    HNSW_EF_CONSTRUCTION,
    HNSW_EF_SEARCH,
    HNSW_M,
)


@dataclass(frozen=True, slots=True)
class IndexDescriptor:
    """What an index holds and how it was built (FR-013).

    The HNSW parameters are stored rather than assumed. Tuning ``m`` upward and
    forgetting is the kind of change that shows up months later as "search got
    slower", with nothing in the deployment to explain it.
    """

    namespace: str
    model: str
    dimension: int
    generation: int = 1
    m: int = HNSW_M
    ef_construction: int = HNSW_EF_CONSTRUCTION
    ef_search: int = HNSW_EF_SEARCH
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """One embedding, its identity, and the metadata searches filter on.

    ``vector_id`` is the identity of the thing embedded — an episode id, a
    knowledge chunk id — not a key the index invents. That is what lets a
    similarity result be resolved back to its record without a second mapping
    table to keep in step.
    """

    vector_id: str
    embedding: tuple[float, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimilarityMatch:
    """One neighbour, with a score where larger means more similar."""

    vector_id: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorIndex(Protocol):
    """Vector storage and similarity search, within one tenant.

    Every namespace is tenant-scoped by the unit of work that produced this
    index. Two organisations declaring a namespace with the same name get two
    indexes, and neither can see the other's vectors (FR-011).
    """

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
        """Declare ``namespace`` if it does not exist, and return its descriptor.

        Idempotent when the declaration matches what is stored. When it does
        not, raises ``EmbeddingDimensionMismatch`` or ``EmbeddingModelMismatch``
        — redeclaring an existing index with a different model is a re-embed,
        and it has to say so. Raises ``BoundExceeded`` above
        ``MAX_INDEXABLE_EMBEDDING_DIMENSION``.
        """

    async def describe(self, namespace: str) -> IndexDescriptor | None:
        """Return the descriptor for ``namespace``, or ``None`` if undeclared."""

    async def upsert(
        self,
        namespace: str,
        records: Sequence[VectorRecord],
        *,
        generation: int | None = None,
    ) -> int:
        """Store ``records`` and return how many were written.

        ``generation`` defaults to the active one; a re-embed passes the
        generation it opened. Raises ``VectorNamespaceUnknown`` when the index
        was never declared, ``EmbeddingDimensionMismatch`` when any record's
        width differs from the declaration, and ``GenerationNotFound`` for a
        generation that was never opened.
        """

    async def delete(self, namespace: str, vector_ids: Sequence[str]) -> int:
        """Delete the named vectors from every generation, and return the count.

        Every generation, not just the active one: an episode deleted for
        retention must not come back when a re-embed is activated.
        """

    async def search(
        self,
        namespace: str,
        embedding: tuple[float, ...],
        *,
        k: int = DEFAULT_VECTOR_TOP_K,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[SimilarityMatch, ...]:
        """Return the ``k`` nearest neighbours in the active generation, best first.

        ``filters`` matches metadata by equality, every key having to match.
        Raises ``BoundExceeded`` above ``MAX_VECTOR_TOP_K`` and
        ``EmbeddingDimensionMismatch`` when the query vector is the wrong width
        — a query is checked exactly as a write is, because a query of the wrong
        shape returns neighbours too.
        """

    async def count(self, namespace: str, *, generation: int | None = None) -> int:
        """Return how many vectors a generation holds, active by default."""

    async def begin_generation(
        self,
        namespace: str,
        *,
        model: str,
        dimension: int,
    ) -> int:
        """Open a new generation for re-embedding and return its number.

        The new generation may have a different model and dimension than the
        active one — that is the point of it. Search is unaffected until
        ``activate_generation``.
        """

    async def activate_generation(self, namespace: str, generation: int) -> IndexDescriptor:
        """Make ``generation`` the one searches read, and return the descriptor.

        Atomic. There is no moment at which a search sees part of one generation
        and part of another. Raises ``GenerationNotFound`` for a generation that
        was never opened.
        """

    async def drop_generation(self, namespace: str, generation: int) -> int:
        """Delete a non-active generation's vectors and return the count.

        Raises ``GenerationNotFound`` when asked to drop the active generation:
        an index with nothing in it answers every search with silence, and
        silence is indistinguishable from "no similar incidents".
        """


__all__ = [
    "IndexDescriptor",
    "SimilarityMatch",
    "VectorIndex",
    "VectorRecord",
]
