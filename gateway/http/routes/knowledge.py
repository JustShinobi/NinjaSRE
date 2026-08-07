"""The knowledge corpus, browsable: which documents exist and what is in one.

Documents and their passages, nothing generated. What an operator wants from
this screen is to check that the runbook the agent quoted is the runbook they
think it is, which is a question about the corpus rather than about a model.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.state import GatewayState
from platform.persistence.ports.knowledge_store import KnowledgeDocument

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class KnowledgeDocumentView(BaseModel):
    document_id: str
    title: str
    checksum: str
    source_uri: str | None = None
    content_type: str
    updated_at: str | None = None
    metadata: dict[str, Any]


class KnowledgeChunkView(BaseModel):
    chunk_id: str
    ordinal: int
    text: str


class KnowledgeDocumentList(BaseModel):
    documents: list[KnowledgeDocumentView]


class KnowledgeDocumentDetail(BaseModel):
    document: KnowledgeDocumentView
    chunks: list[KnowledgeChunkView]


def _view(document: KnowledgeDocument) -> KnowledgeDocumentView:
    return KnowledgeDocumentView(
        document_id=document.document_id,
        title=document.title,
        checksum=document.checksum,
        source_uri=document.source_uri,
        content_type=document.content_type,
        updated_at=document.updated_at.isoformat() if document.updated_at else None,
        metadata=dict(document.metadata),
    )


@router.get("/documents", response_model=KnowledgeDocumentList)
async def list_documents(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = 50,
) -> KnowledgeDocumentList:
    """Return the ingested documents (FR-015)."""
    async with state.gateway.begin(auth.scope) as uow:
        documents = await uow.knowledge.list_documents(limit=limit)
    return KnowledgeDocumentList(documents=[_view(document) for document in documents])


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
async def get_document(
    document_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> KnowledgeDocumentDetail:
    """Return one document with its passages, in document order.

    Ordered because a passage read without its neighbours is how a conditional
    instruction becomes an unconditional one.
    """
    async with state.gateway.begin(auth.scope) as uow:
        document = await uow.knowledge.get_document(document_id)
        if document is None:
            raise not_found(f"no knowledge document {document_id!r}")
        chunks = await uow.knowledge.chunks_for_document(document_id)
    return KnowledgeDocumentDetail(
        document=_view(document),
        chunks=[
            KnowledgeChunkView(chunk_id=chunk.chunk_id, ordinal=chunk.ordinal, text=chunk.text)
            for chunk in sorted(chunks, key=lambda chunk: chunk.ordinal)
        ],
    )


__all__ = ["router"]
