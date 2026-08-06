"""The knowledge base: chunking, ingestion, hierarchy, citable search, and sync.

A document is what the operator gave us; a chunk is what retrieval returns; a
citation is what the agent is expected to quote. The three are separate types on
purpose — a search result that could not name its section is a search result the
agent has to paraphrase, and a paraphrased procedure is a procedure nobody wrote.

Ingestion is where the boundary is: every document passes the guardrail engine on
the way in, and one carrying a detected secret is refused with the location
reported rather than stored with the secret redacted. A redacted runbook is a
runbook with a hole in it that nobody knows about; a refused one is a message to
whoever pasted the credential.
"""

from __future__ import annotations

from platform.knowledge.base.chunking import Section, TextChunk, chunk_document, sections
from platform.knowledge.base.ingestion import (
    IngestionOutcome,
    IngestionResult,
    KnowledgeIngestor,
    SecretLocation,
)
from platform.knowledge.base.models import (
    Chunk,
    Citation,
    Document,
    DocumentOrigin,
    DocumentType,
    TreeNode,
    checksum_of,
)
from platform.knowledge.base.search import (
    KnowledgeLedger,
    KnowledgeQuery,
    KnowledgeRecord,
    KnowledgeResult,
    KnowledgeSearch,
    RetrievedChunk,
)
from platform.knowledge.base.sync import (
    ConfluenceSource,
    DocumentSource,
    GitMarkdownSource,
    GoogleDocsSource,
    KnowledgeSync,
    NotionSource,
    SourceDocument,
    SyncReport,
)
from platform.knowledge.base.tree import KnowledgeTree, build_tree, flatten

__all__ = [
    "Chunk",
    "Citation",
    "ConfluenceSource",
    "Document",
    "DocumentOrigin",
    "DocumentSource",
    "DocumentType",
    "GitMarkdownSource",
    "GoogleDocsSource",
    "IngestionOutcome",
    "IngestionResult",
    "KnowledgeIngestor",
    "KnowledgeLedger",
    "KnowledgeQuery",
    "KnowledgeRecord",
    "KnowledgeResult",
    "KnowledgeSearch",
    "KnowledgeSync",
    "KnowledgeTree",
    "NotionSource",
    "RetrievedChunk",
    "SecretLocation",
    "Section",
    "SourceDocument",
    "SyncReport",
    "TextChunk",
    "TreeNode",
    "build_tree",
    "checksum_of",
    "chunk_document",
    "flatten",
    "sections",
]
