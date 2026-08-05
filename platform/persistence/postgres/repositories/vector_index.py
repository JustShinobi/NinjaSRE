"""Similarity search over pgvector, one table per generation.

pgvector fixes a column's dimension when the column is created, and FR-014 says
a re-embed may change it without search going down. Those two facts together
rule out a single ``vectors`` table with a generation column, and they are why
each generation gets a table of its own:

- ``begin_generation`` creates one, with that model's width and its own HNSW
  index. Writes land there while searches keep reading the active table.
- ``activate_generation`` moves one integer in ``vector_indexes``. There is no
  moment at which a search sees half of each.
- ``drop_generation`` is a ``DROP TABLE``, which reclaims the space at once
  rather than leaving a bloated heap to vacuum.

Table names are built from the namespace by ``identifiers.vector_table_name``,
which validates rather than escapes. Namespaces come from constants today; the
validation is what makes that safe to stop checking tomorrow.

Vectors bind as their text form — ``'[0.1,0.2]'`` — which pgvector casts. That
avoids registering a codec on every pooled connection, and a codec that is
registered on some connections and not others is a bug that appears under load.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

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
from platform.persistence.ports.vector_index import (
    IndexDescriptor,
    SimilarityMatch,
    VectorRecord,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.identifiers import quoted, vector_table_name
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    rows_affected,
    utc_now,
)


def encode(embedding: Sequence[float]) -> str:
    """Return the literal form pgvector parses."""
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


@dataclass(slots=True)
class PostgresVectorIndex(TenantBound):
    """Vector namespaces for one organisation."""

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
        _check_dimension(dimension)

        index = await self.session.get(models.VectorIndexRow, (self.org_id, namespace))
        if index is not None:
            generation = await self._require_generation(namespace, index.active_generation)
            if generation.dimension != dimension:
                raise EmbeddingDimensionMismatch(
                    namespace=namespace, expected=generation.dimension, found=dimension
                )
            if generation.model != model:
                raise EmbeddingModelMismatch(
                    namespace=namespace, expected=generation.model, found=model
                )
            return _describe(index, generation)

        created_at = utc_now()
        index = models.VectorIndexRow(
            org_id=self.org_id,
            namespace=namespace,
            active_generation=1,
            m=m,
            ef_construction=ef_construction,
            ef_search=ef_search,
            created_at=created_at,
        )
        self.session.add(index)
        await self.session.flush()

        generation = await self._create_generation(
            namespace, generation=1, model=model, dimension=dimension, created_at=created_at
        )
        return _describe(index, generation)

    async def describe(self, namespace: str) -> IndexDescriptor | None:
        """Return the descriptor for ``namespace``, or ``None`` if undeclared."""
        index = await self.session.get(models.VectorIndexRow, (self.org_id, namespace))
        if index is None:
            return None
        generation = await self._require_generation(namespace, index.active_generation)
        return _describe(index, generation)

    async def upsert(
        self,
        namespace: str,
        records: Sequence[VectorRecord],
        *,
        generation: int | None = None,
    ) -> int:
        """Store ``records`` and return how many were written."""
        index = await self._require_index(namespace)
        number = index.active_generation if generation is None else generation
        row = await self._require_generation(namespace, number)

        # Validated in full before anything is written. A partial batch would
        # leave the caller unable to tell which half landed.
        for record in records:
            if len(record.embedding) != row.dimension:
                raise EmbeddingDimensionMismatch(
                    namespace=namespace,
                    expected=row.dimension,
                    found=len(record.embedding),
                )

        table = quoted(row.table_name)
        for record in records:
            await self.session.execute(
                text(
                    f"INSERT INTO {table} (org_id, vector_id, embedding, metadata) "
                    f"VALUES (:org_id, :vector_id, CAST(:embedding AS vector), "
                    f"CAST(:metadata AS jsonb)) "
                    f"ON CONFLICT (org_id, vector_id) DO UPDATE SET "
                    f"embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata"
                ),
                {
                    "org_id": self.org_id,
                    "vector_id": record.vector_id,
                    "embedding": encode(record.embedding),
                    "metadata": json.dumps(dict(record.metadata)),
                },
            )
        return len(records)

    async def delete(self, namespace: str, vector_ids: Sequence[str]) -> int:
        """Delete the named vectors from every generation, and return the count."""
        await self._require_index(namespace)
        if not vector_ids:
            return 0

        removed = 0
        for row in await self._generations(namespace):
            # Every generation, not just the active one: an episode deleted for
            # retention must not come back when a re-embed is activated.
            result = await self.session.execute(
                text(
                    f"DELETE FROM {quoted(row.table_name)} "
                    f"WHERE org_id = :org_id AND vector_id = ANY(:ids)"
                ),
                {"org_id": self.org_id, "ids": list(vector_ids)},
            )
            removed += rows_affected(result)
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

        index = await self._require_index(namespace)
        generation = await self._require_generation(namespace, index.active_generation)
        if len(embedding) != generation.dimension:
            raise EmbeddingDimensionMismatch(
                namespace=namespace, expected=generation.dimension, found=len(embedding)
            )

        # ``ef_search`` must be at least ``k`` or HNSW returns fewer neighbours
        # than asked for. Set per transaction, so a tuned index is honoured
        # without leaking the setting onto a pooled connection.
        await self.session.execute(text(f"SET LOCAL hnsw.ef_search = {max(index.ef_search, k)}"))

        # ``<=>`` is cosine *distance*, in [0, 2]. The port promises a
        # similarity in [0, 1] where larger is nearer, so the conversion happens
        # here rather than in every caller — one of whom would sort the wrong
        # way round.
        clause = "WHERE org_id = :org_id"
        parameters: dict[str, Any] = {
            "org_id": self.org_id,
            "embedding": encode(embedding),
            "k": k,
        }
        if filters:
            clause += " AND metadata @> CAST(:filters AS jsonb)"
            parameters["filters"] = json.dumps(dict(filters))

        rows = await self.session.execute(
            text(
                f"SELECT vector_id, metadata, "
                f"1.0 - (embedding <=> CAST(:embedding AS vector)) / 2.0 AS score "
                f"FROM {quoted(generation.table_name)} {clause} "
                f"ORDER BY embedding <=> CAST(:embedding AS vector), vector_id "
                f"LIMIT :k"
            ),
            parameters,
        )
        return tuple(
            SimilarityMatch(
                vector_id=vector_id,
                score=float(score),
                metadata=dict(metadata or {}),
            )
            for vector_id, metadata, score in rows.all()
        )

    async def count(self, namespace: str, *, generation: int | None = None) -> int:
        """Return how many vectors a generation holds, active by default."""
        index = await self._require_index(namespace)
        number = index.active_generation if generation is None else generation
        row = await self._require_generation(namespace, number)

        total = await self.session.scalar(
            text(f"SELECT count(*) FROM {quoted(row.table_name)} WHERE org_id = :org_id"),
            {"org_id": self.org_id},
        )
        return int(total or 0)

    async def begin_generation(
        self,
        namespace: str,
        *,
        model: str,
        dimension: int,
    ) -> int:
        """Open a new generation for re-embedding and return its number."""
        _check_dimension(dimension)
        await self._require_index(namespace)

        existing = await self._generations(namespace)
        number = max(row.generation for row in existing) + 1
        await self._create_generation(
            namespace,
            generation=number,
            model=model,
            dimension=dimension,
            created_at=utc_now(),
        )
        return number

    async def activate_generation(self, namespace: str, generation: int) -> IndexDescriptor:
        """Make ``generation`` the one searches read, and return the descriptor."""
        index = await self._require_index(namespace)
        row = await self._require_generation(namespace, generation)
        index.active_generation = generation
        await self.session.flush()
        return _describe(index, row)

    async def drop_generation(self, namespace: str, generation: int) -> int:
        """Delete a non-active generation's vectors and return the count."""
        index = await self._require_index(namespace)
        if generation == index.active_generation:
            # An index with nothing in it answers every search with silence, and
            # silence is indistinguishable from "no similar incidents".
            raise GenerationNotFound(namespace=namespace, generation=generation)

        row = await self._require_generation(namespace, generation)
        dropped = await self.count(namespace, generation=generation)
        await self.session.execute(text(f"DROP TABLE IF EXISTS {quoted(row.table_name)}"))
        await self.session.delete(row)
        await self.session.flush()
        return dropped

    # --- internals ------------------------------------------------------------

    async def _require_index(self, namespace: str) -> models.VectorIndexRow:
        index = await self.session.get(models.VectorIndexRow, (self.org_id, namespace))
        if index is None:
            raise VectorNamespaceUnknown(namespace)
        return index

    async def _require_generation(
        self, namespace: str, generation: int
    ) -> models.VectorGenerationRow:
        row = await self.session.get(
            models.VectorGenerationRow, (self.org_id, namespace, generation)
        )
        if row is None:
            raise GenerationNotFound(namespace=namespace, generation=generation)
        return row

    async def _generations(self, namespace: str) -> list[models.VectorGenerationRow]:
        rows = await self.session.scalars(
            select(models.VectorGenerationRow)
            .where(
                models.VectorGenerationRow.org_id == self.org_id,
                models.VectorGenerationRow.namespace == namespace,
            )
            .order_by(models.VectorGenerationRow.generation)
        )
        return list(rows)

    async def _create_generation(
        self,
        namespace: str,
        *,
        generation: int,
        model: str,
        dimension: int,
        created_at: Any,
    ) -> models.VectorGenerationRow:
        """Create a generation's table, its HNSW index, and its metadata row."""
        table_name = vector_table_name(namespace, generation)
        index = await self._require_index(namespace)
        table = quoted(table_name)

        await self.session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {table} ("
                f"org_id text NOT NULL, "
                f"vector_id text NOT NULL, "
                f"embedding vector({dimension}) NOT NULL, "
                f"metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb, "
                f"PRIMARY KEY (org_id, vector_id))"
            )
        )
        # Not CONCURRENTLY: the table was created in this transaction and has no
        # rows, so there is nothing to block. FR-008's concurrent build is for
        # indexes added to tables that already hold data, and those are
        # migrations.
        await self.session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {quoted(table_name + '_hnsw')} "
                f"ON {table} USING hnsw (embedding vector_cosine_ops) "
                f"WITH (m = {index.m}, ef_construction = {index.ef_construction})"
            )
        )

        row = models.VectorGenerationRow(
            org_id=self.org_id,
            namespace=namespace,
            generation=generation,
            model=model,
            dimension=dimension,
            table_name=table_name,
            created_at=created_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row


def _describe(
    index: models.VectorIndexRow, generation: models.VectorGenerationRow
) -> IndexDescriptor:
    return IndexDescriptor(
        namespace=index.namespace,
        model=generation.model,
        dimension=generation.dimension,
        generation=generation.generation,
        m=index.m,
        ef_construction=index.ef_construction,
        ef_search=index.ef_search,
        created_at=as_utc(index.created_at),
    )


def _check_dimension(dimension: int) -> int:
    if dimension > MAX_INDEXABLE_EMBEDDING_DIMENSION:
        raise BoundExceeded(
            parameter="dimension",
            requested=dimension,
            limit=MAX_INDEXABLE_EMBEDDING_DIMENSION,
            constant="MAX_INDEXABLE_EMBEDDING_DIMENSION",
        )
    if dimension < 1:
        raise ValueError(f"An index needs at least one dimension, got {dimension}.")
    return dimension


__all__ = ["PostgresVectorIndex", "encode"]
