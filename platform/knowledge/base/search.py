"""Finding a passage, and returning enough of it that the agent can cite it.

Similarity search over chunks, team-scoped, with three properties that are each a
requirement rather than a step.

**Every result is citable** (FR-013). A chunk comes back with its document, its
section, and a resolvable location — assembled once, here, rather than formatted
at each of the three places a result is shown. An agent handed a passage without
its source has no way to quote it, so it paraphrases, and a paraphrased procedure
is a procedure nobody wrote and nobody can check.

**One document cannot own the answer.** A runbook that repeats a phrase across
six sections would otherwise win every slot, and the answer stops being a search
over the corpus and becomes a search within one file.
``MAX_CHUNKS_PER_DOCUMENT`` is what keeps a second opinion in the result.

**The scope is checked twice.** The organisation boundary is structural — no
repository port takes an ``org_id`` — and the team boundary is a metadata filter
inside the index *plus* a check on the document every surviving chunk belongs to.
Belt and braces on purpose: the filter is what makes it fast and the check is
what makes it true, and a filter that silently stopped being applied would leak
without either failing.

An empty result is a result. No documentation about this failure is the common
case for the first weeks of any deployment, and it has to come back as an empty
tuple with ``searched=True`` rather than as an unavailability. The distinction
the agent needs is between "nobody wrote about this" and "there was nowhere to
look", and only the second is a reason to change what it does next.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.knowledge import (
    DEFAULT_KNOWLEDGE_SEARCH_RESULTS,
    KNOWLEDGE_SEARCH_CANDIDATE_FACTOR,
    MAX_CHUNKS_PER_DOCUMENT,
    MAX_KNOWLEDGE_SEARCH_RESULTS,
)
from config.constants.persistence import KNOWLEDGE_VECTOR_NAMESPACE, MAX_VECTOR_TOP_K
from config.prompts.knowledge import KNOWLEDGE_DISABLED
from platform.knowledge.base.models import (
    DOCUMENT_TYPE_KEY,
    TEAM_KEY,
    Chunk,
    Citation,
    Document,
    DocumentType,
)
from platform.knowledge.clock import now as _utc_now
from platform.knowledge.policy import KnowledgePolicy
from platform.memory.embeddings.port import Embedder, embed_one
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError, VectorNamespaceUnknown
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import SimilarityMatch

logger = get_logger(__name__)


def bounded_limit(requested: int) -> int:
    """Return the number of passages a request may have, within the ceilings."""
    if requested <= 0:
        return DEFAULT_KNOWLEDGE_SEARCH_RESULTS
    return min(requested, MAX_KNOWLEDGE_SEARCH_RESULTS)


def candidate_count(limit: int) -> int:
    """Return how many neighbours to fetch before the per-document cap cuts them.

    More than the answer needs, because collapsing a document's runs of similar
    chunks has to have something left to promote in their place. Capped at the
    index's own ceiling so the multiplier can never turn a large request into a
    refused one.
    """
    return min(limit * KNOWLEDGE_SEARCH_CANDIDATE_FACTOR, MAX_VECTOR_TOP_K)


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    """What the agent asked the knowledge base for.

    ``document_type`` is a filter rather than a weight: an agent that wants a
    procedure and gets a post-mortem about the same service has been given the
    wrong kind of document, and ranking cannot express "wrong kind" as a
    penalty an operator would recognise.
    """

    text: str
    document_type: str = ""
    limit: int = 0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a knowledge search must carry a query")


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One passage, its citation, and how similar it was."""

    chunk: Chunk
    citation: Citation
    score: float = 0.0

    @property
    def document_id(self) -> str:
        """Return the document this passage came from."""
        return self.chunk.document_id


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    """What one search returned, and whether it ran at all."""

    query: KnowledgeQuery
    chunks: tuple[RetrievedChunk, ...] = ()
    searched: bool = True
    reason: str = ""

    @property
    def empty(self) -> bool:
        """Return whether the search matched nothing."""
        return not self.chunks

    @property
    def documents(self) -> tuple[str, ...]:
        """Return the documents this result draws on, in rank order, once each."""
        seen: dict[str, None] = {}
        for found in self.chunks:
            seen.setdefault(found.document_id, None)
        return tuple(seen)


@dataclass(slots=True)
class KnowledgeRecord:
    """One knowledge search as the run trace records it (FR-023)."""

    query: str
    document_type: str = ""
    returned: tuple[str, ...] = ()
    documents: tuple[str, ...] = ()
    searched: bool = True
    reason: str = ""
    acted_on: bool = False

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this search."""
        return {
            "query": self.query,
            "document_type": self.document_type,
            "returned": list(self.returned),
            "documents": list(self.documents),
            "searched": self.searched,
            "reason": self.reason,
            "acted_on": self.acted_on,
        }


@dataclass(slots=True)
class KnowledgeLedger:
    """Every knowledge search one run made, and which of them it went on to use.

    Run-scoped and mutable, like the recall ledger episodic memory keeps and for
    the same reason: a deployment where the knowledge base is searched constantly
    and never cited is one where the corpus or the chunking is wrong, and nothing
    else in the system would say so.
    """

    records: list[KnowledgeRecord] = field(default_factory=list)

    def record(self, result: KnowledgeResult) -> KnowledgeRecord:
        """Store ``result`` and return the record it produced."""
        entry = KnowledgeRecord(
            query=result.query.text,
            document_type=result.query.document_type,
            returned=tuple(found.chunk.chunk_id for found in result.chunks),
            documents=result.documents,
            searched=result.searched,
            reason=result.reason,
        )
        self.records.append(entry)
        return entry

    def mark_acted_on(self, text: str) -> int:
        """Mark every search whose documents ``text`` cites, and return how many.

        Matched on the citation location, which is what the guidance asks the
        agent to reproduce. Crude and correct for what it is asked: a location is
        a generated reference that does not occur by accident, so an answer
        containing one either cited it or was shown it and repeated it — and
        either way the search reached the conclusion.
        """
        marked = 0
        for entry in self.records:
            if entry.acted_on or not entry.documents:
                continue
            if any(document in text for document in entry.documents):
                entry.acted_on = True
                marked += 1
        return marked

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about knowledge-base use."""
        return {
            "knowledge_searches": len(self.records),
            "knowledge_searches_with_results": sum(1 for e in self.records if e.returned),
            "knowledge_searches_acted_on": sum(1 for e in self.records if e.acted_on),
            "knowledge_records": [entry.to_record() for entry in self.records],
        }


@dataclass(slots=True)
class KnowledgeSearch:
    """Team-scoped, citable retrieval over one team's documents."""

    gateway: PersistenceGateway
    scope: TenantScope
    embedder: Embedder
    policy: KnowledgePolicy = field(default_factory=KnowledgePolicy)
    ledger: KnowledgeLedger = field(default_factory=KnowledgeLedger)
    clock: Callable[[], datetime] = _utc_now

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: knowledge search must be scoped to a team — an "
                "unscoped search is one that can return another team's runbooks"
            )

    async def search(self, query: KnowledgeQuery, *, record: bool = True) -> KnowledgeResult:
        """Return the passages resembling ``query``, citable and team-scoped.

        Three outcomes. Passages are something to cite. An empty search means
        nobody has written about this failure, which is a normal result. A search
        that did not run at all — switched off, or a store that could not be
        reached — is not a statement about the corpus, and returning it as an
        empty result would teach the agent that the team has no documentation.
        """
        if not self.policy.knowledge_enabled:
            return self._recorded(
                KnowledgeResult(query=query, searched=False, reason=KNOWLEDGE_DISABLED),
                record=record,
            )

        limit = bounded_limit(query.limit)
        try:
            matches = await self._neighbours(query, limit=limit)
            chunks = await self._resolve(matches, limit=limit)
        except VectorNamespaceUnknown:
            # A team that has never ingested a document has no namespace. That
            # is an empty corpus, not an unavailability — and it is what every
            # deployment's first weeks look like.
            logger.info("knowledge.corpus_empty", team=self.scope.team_node_id)
            return self._recorded(KnowledgeResult(query=query), record=record)
        except PersistenceError as error:
            logger.warning("knowledge.search_unavailable", error=str(error))
            return self._recorded(
                KnowledgeResult(query=query, searched=False, reason=str(error)), record=record
            )

        logger.info(
            "knowledge.searched",
            query=query.text,
            document_type=query.document_type,
            returned=len(chunks),
        )
        return self._recorded(KnowledgeResult(query=query, chunks=chunks), record=record)

    async def _neighbours(
        self, query: KnowledgeQuery, *, limit: int
    ) -> tuple[SimilarityMatch, ...]:
        """Return the raw similarity matches, filtered inside the index."""
        embedding = await embed_one(self.embedder, query.text)
        filters: dict[str, Any] = {TEAM_KEY: self.scope.team_node_id}
        if query.document_type.strip():
            filters[DOCUMENT_TYPE_KEY] = DocumentType.parse(query.document_type).value

        async with self.gateway.begin(self.scope) as uow:
            return await uow.vectors.search(
                KNOWLEDGE_VECTOR_NAMESPACE,
                embedding,
                k=candidate_count(limit),
                filters=filters,
            )

    async def _resolve(
        self, matches: Sequence[SimilarityMatch], *, limit: int
    ) -> tuple[RetrievedChunk, ...]:
        """Return the matched chunks with their citations, capped per document."""
        if not matches:
            return ()

        found: list[RetrievedChunk] = []
        per_document: dict[str, int] = {}
        documents: dict[str, Document | None] = {}

        async with self.gateway.begin(self.scope) as uow:
            for match in matches:
                if len(found) >= limit:
                    break
                stored = await uow.knowledge.get_chunk(match.vector_id)
                if stored is None:
                    # A vector whose chunk is gone. Ingestion replaces chunks and
                    # their vectors in one unit of work, so this is a corpus
                    # mid-sweep rather than an error — skip it and say so.
                    logger.info("knowledge.dangling_vector", chunk=match.vector_id)
                    continue

                chunk = Chunk.from_stored(stored)
                if per_document.get(chunk.document_id, 0) >= MAX_CHUNKS_PER_DOCUMENT:
                    continue

                if chunk.document_id not in documents:
                    record = await uow.knowledge.get_document(chunk.document_id)
                    documents[chunk.document_id] = (
                        Document.from_stored(record, org_id=self.scope.org_id)
                        if record is not None
                        else None
                    )
                document = documents[chunk.document_id]
                if document is None or not self._visible(document):
                    continue

                per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1
                found.append(
                    RetrievedChunk(
                        chunk=chunk, citation=citation_for(document, chunk), score=match.score
                    )
                )

        return tuple(found)

    def _visible(self, document: Document) -> bool:
        """Return whether this team is allowed to see ``document``.

        Checked against the document, not only against the metadata the index
        filter used. A metadata value is a copy written at ingestion time; the
        document is the fact, and the two disagreeing is exactly the case a
        filter alone would miss.
        """
        if document.team_node_id == self.scope.team_node_id:
            return True
        logger.warning(
            "knowledge.cross_team_match_refused",
            document=document.document_id,
            requesting_team=self.scope.team_node_id,
        )
        return False

    def _recorded(self, result: KnowledgeResult, *, record: bool = True) -> KnowledgeResult:
        """Store ``result`` in the run's ledger and return it unchanged."""
        if record:
            self.ledger.record(result)
        return result


def citation_for(document: Document, chunk: Chunk) -> Citation:
    """Return where a passage came from, in the form the agent quotes."""
    return Citation(
        document_id=document.document_id,
        title=document.title,
        section=chunk.section,
        location=document.location,
        document_type=document.document_type,
        origin=document.origin,
        updated_at=document.updated_at,
    )


__all__ = [
    "KnowledgeLedger",
    "KnowledgeQuery",
    "KnowledgeRecord",
    "KnowledgeResult",
    "KnowledgeSearch",
    "RetrievedChunk",
    "bounded_limit",
    "candidate_count",
    "citation_for",
]
