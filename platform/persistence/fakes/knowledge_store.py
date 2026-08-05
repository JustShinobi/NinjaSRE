"""In-memory knowledge documents and chunks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.errors import RecordNotFound
from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.knowledge_store import KnowledgeChunk, KnowledgeDocument

#: Sorts before any real timestamp, so a document with no recorded update falls
#: to the end of a "most recently updated first" listing.
_UNDATED = datetime.min.replace(tzinfo=UTC)


@dataclass(slots=True)
class FakeKnowledgeStore:
    """Documents and chunks for one organisation."""

    org_id: str
    state: TenantState

    async def upsert_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        """Store ``document``, replacing any earlier version, and return it."""
        check_payload(document.metadata, kind="knowledge document metadata")
        stored = (
            document
            if document.updated_at is not None
            else replace(document, updated_at=datetime.now(UTC))
        )
        self.state.documents[document.document_id] = stored
        return stored

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        """Return the document with ``document_id``, or ``None``."""
        return self.state.documents.get(document_id)

    async def find_document_by_uri(self, source_uri: str) -> KnowledgeDocument | None:
        """Return the document ingested from ``source_uri``, or ``None``."""
        return next(
            (d for d in self.state.documents.values() if d.source_uri == source_uri),
            None,
        )

    async def list_documents(self, *, limit: int = 50) -> tuple[KnowledgeDocument, ...]:
        """Return documents, most recently updated first."""
        check_limit(limit)
        found = sorted(
            self.state.documents.values(),
            key=lambda d: (d.updated_at or _UNDATED, d.document_id),
            reverse=True,
        )
        return tuple(found[:limit])

    async def delete_document(self, document_id: str) -> bool:
        """Delete the document and its chunks, and return whether it existed."""
        if self.state.documents.pop(document_id, None) is None:
            return False
        for chunk_id in [
            chunk_id
            for chunk_id, chunk in self.state.chunks.items()
            if chunk.document_id == document_id
        ]:
            del self.state.chunks[chunk_id]
        return True

    async def replace_chunks(
        self,
        document_id: str,
        chunks: Sequence[KnowledgeChunk],
    ) -> tuple[KnowledgeChunk, ...]:
        """Make ``chunks`` the document's entire chunk set, and return it."""
        if document_id not in self.state.documents:
            raise RecordNotFound(kind="knowledge document", identifier=document_id)

        for chunk in chunks:
            check_payload(chunk.metadata, kind="knowledge chunk metadata")

        for chunk_id in [
            chunk_id
            for chunk_id, chunk in self.state.chunks.items()
            if chunk.document_id == document_id
        ]:
            del self.state.chunks[chunk_id]

        for chunk in chunks:
            self.state.chunks[chunk.chunk_id] = chunk
        return await self.chunks_for_document(document_id)

    async def chunks_for_document(self, document_id: str) -> tuple[KnowledgeChunk, ...]:
        """Return the document's chunks in ordinal order."""
        owned = [c for c in self.state.chunks.values() if c.document_id == document_id]
        return tuple(sorted(owned, key=lambda c: (c.ordinal, c.chunk_id)))

    async def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        """Return the chunk with ``chunk_id``, or ``None``."""
        return self.state.chunks.get(chunk_id)

    async def count_chunks(self) -> int:
        """Return how many chunks this tenant holds."""
        return len(self.state.chunks)


__all__ = ["FakeKnowledgeStore"]
