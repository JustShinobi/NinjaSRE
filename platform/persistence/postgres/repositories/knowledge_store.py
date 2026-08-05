"""Knowledge documents and chunks over PostgreSQL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select

from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.knowledge_store import KnowledgeChunk, KnowledgeDocument
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    check_limit,
    translating,
    utc_now,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _to_document(row: models.KnowledgeDocument) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=row.document_id,
        title=row.title,
        checksum=row.checksum,
        source_uri=row.source_uri,
        content_type=row.content_type,
        updated_at=as_utc(row.updated_at),
        metadata=dict(row.document_metadata),
    )


def _to_chunk(row: models.KnowledgeChunk) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        ordinal=row.ordinal,
        text=row.text,
        metadata=dict(row.chunk_metadata),
    )


@dataclass(slots=True)
class PostgresKnowledgeStore(TenantBound):
    """Documents and chunks for one organisation."""

    async def upsert_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        """Store ``document``, replacing any earlier version, and return it."""
        row = await self.session.get(models.KnowledgeDocument, (self.org_id, document.document_id))
        if row is None:
            row = models.KnowledgeDocument(org_id=self.org_id, document_id=document.document_id)
            self.session.add(row)

        row.title = document.title
        row.checksum = document.checksum
        row.source_uri = document.source_uri
        row.content_type = document.content_type
        row.updated_at = document.updated_at or utc_now()
        row.document_metadata = check_payload(document.metadata, kind="knowledge document metadata")

        await self.session.flush()
        return _to_document(row)

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        """Return the document with ``document_id``, or ``None``."""
        row = await self.session.get(models.KnowledgeDocument, (self.org_id, document_id))
        return _to_document(row) if row is not None else None

    async def find_document_by_uri(self, source_uri: str) -> KnowledgeDocument | None:
        """Return the document ingested from ``source_uri``, or ``None``."""
        row = await self.session.scalar(
            select(models.KnowledgeDocument).where(
                models.KnowledgeDocument.org_id == self.org_id,
                models.KnowledgeDocument.source_uri == source_uri,
            )
        )
        return _to_document(row) if row is not None else None

    async def list_documents(self, *, limit: int = 50) -> tuple[KnowledgeDocument, ...]:
        """Return documents, most recently updated first."""
        check_limit(limit)
        rows = await self.session.scalars(
            select(models.KnowledgeDocument)
            .where(models.KnowledgeDocument.org_id == self.org_id)
            .order_by(
                models.KnowledgeDocument.updated_at.desc(),
                models.KnowledgeDocument.document_id.desc(),
            )
            .limit(limit)
        )
        return tuple(_to_document(row) for row in rows)

    async def delete_document(self, document_id: str) -> bool:
        """Delete the document and its chunks, and return whether it existed.

        The chunks go by cascade on the composite foreign key. Doing it in the
        database rather than in two statements means a document can never be
        gone while its chunks remain — which would leave passages retrievable
        with no provenance to show beside them.
        """
        row = await self.session.get(models.KnowledgeDocument, (self.org_id, document_id))
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def replace_chunks(
        self,
        document_id: str,
        chunks: Sequence[KnowledgeChunk],
    ) -> tuple[KnowledgeChunk, ...]:
        """Make ``chunks`` the document's entire chunk set, and return it."""
        if await self.session.get(models.KnowledgeDocument, (self.org_id, document_id)) is None:
            raise RecordNotFound(kind="knowledge document", identifier=document_id)

        for chunk in chunks:
            check_payload(chunk.metadata, kind="knowledge chunk metadata")

        # Delete then insert, in one transaction. A section removed from a
        # runbook must not stay retrievable, confident, and describing a
        # procedure that no longer exists.
        await self.session.execute(
            delete(models.KnowledgeChunk).where(
                models.KnowledgeChunk.org_id == self.org_id,
                models.KnowledgeChunk.document_id == document_id,
            )
        )
        await self.session.flush()

        for chunk in chunks:
            self.session.add(
                models.KnowledgeChunk(
                    org_id=self.org_id,
                    chunk_id=chunk.chunk_id,
                    document_id=document_id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    chunk_metadata=dict(chunk.metadata),
                )
            )
        with translating(
            kind="knowledge chunk", identifier=document_id, referenced="knowledge document"
        ):
            await self.session.flush()

        return await self.chunks_for_document(document_id)

    async def chunks_for_document(self, document_id: str) -> tuple[KnowledgeChunk, ...]:
        """Return the document's chunks in ordinal order."""
        rows = await self.session.scalars(
            select(models.KnowledgeChunk)
            .where(
                models.KnowledgeChunk.org_id == self.org_id,
                models.KnowledgeChunk.document_id == document_id,
            )
            .order_by(models.KnowledgeChunk.ordinal, models.KnowledgeChunk.chunk_id)
        )
        return tuple(_to_chunk(row) for row in rows)

    async def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        """Return the chunk with ``chunk_id``, or ``None``."""
        row = await self.session.get(models.KnowledgeChunk, (self.org_id, chunk_id))
        return _to_chunk(row) if row is not None else None

    async def count_chunks(self) -> int:
        """Return how many chunks this tenant holds."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(models.KnowledgeChunk)
            .where(models.KnowledgeChunk.org_id == self.org_id)
        )
        return int(total or 0)


__all__ = ["PostgresKnowledgeStore"]
