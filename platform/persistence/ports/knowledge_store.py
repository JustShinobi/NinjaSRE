"""Runbooks, architecture notes, and post-mortems, chunked for retrieval.

A document is what the operator gave us; a chunk is what retrieval actually
returns. Both are stored, because answering "where did this come from" needs the
document and answering "what is relevant here" needs the chunk, and reconstructing
either from the other loses something.

Chunks are replaced wholesale rather than upserted individually. Re-ingesting a
runbook whose middle section was deleted would otherwise leave that section in
the index forever — retrievable, confident, and describing a procedure that no
longer exists. ``replace_chunks`` makes the new set the whole set, which is the
only version of this operation that cannot leave a stale chunk behind.

``checksum`` is how re-ingestion stays cheap. A document whose checksum has not
moved does not need re-chunking or re-embedding, and the operator syncing a
hundred runbooks nightly pays for the ones that changed.

As with episodes, the embeddings are not here. Chunk vectors live in the
``knowledge`` namespace of ``VectorIndex``, keyed by ``chunk_id``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One source document, as ingested."""

    document_id: str
    title: str
    checksum: str
    source_uri: str | None = None
    content_type: str = "text/markdown"
    updated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """One retrievable passage of a document.

    ``ordinal`` is its position in the document, kept so a retrieved chunk can
    be shown with what surrounds it. A passage quoted without its neighbours is
    how a conditional instruction becomes an unconditional one.
    """

    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class KnowledgeStore(Protocol):
    """Knowledge documents and their chunks, within one tenant."""

    async def upsert_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        """Store ``document``, replacing any earlier version, and return it."""

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        """Return the document with ``document_id``, or ``None``."""

    async def find_document_by_uri(self, source_uri: str) -> KnowledgeDocument | None:
        """Return the document ingested from ``source_uri``, or ``None``."""

    async def list_documents(self, *, limit: int = 50) -> tuple[KnowledgeDocument, ...]:
        """Return documents, most recently updated first."""

    async def delete_document(self, document_id: str) -> bool:
        """Delete the document and its chunks, and return whether it existed.

        Cascades on purpose, which is the opposite of the config hierarchy's
        refusal to. A chunk without its document has no provenance and cannot
        be shown to anybody, so keeping it would preserve nothing.
        """

    async def replace_chunks(
        self,
        document_id: str,
        chunks: Sequence[KnowledgeChunk],
    ) -> tuple[KnowledgeChunk, ...]:
        """Make ``chunks`` the document's entire chunk set, and return it.

        Raises ``RecordNotFound`` when the document does not exist in this
        tenant. The chunk ids that disappear are returned to the caller's
        attention by way of ``chunks_for_document`` before the call — deleting
        their vectors is the caller's second step, and doing both in one unit of
        work is what keeps the index and the store in agreement.
        """

    async def chunks_for_document(self, document_id: str) -> tuple[KnowledgeChunk, ...]:
        """Return the document's chunks in ordinal order."""

    async def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        """Return the chunk with ``chunk_id``, or ``None``.

        This is what turns a similarity match back into text. A search returns
        chunk ids; something has to resolve them, and doing it here keeps the
        vector index free of a copy of the corpus.
        """

    async def count_chunks(self) -> int:
        """Return how many chunks this tenant holds."""


__all__ = [
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeStore",
]
