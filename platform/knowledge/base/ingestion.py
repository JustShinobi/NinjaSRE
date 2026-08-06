"""Getting a document in: screened, chunked, embedded, and superseding its last version.

The boundary is here, and it is the reason ingestion is one module rather than a
call to the chunker followed by a call to the store.

**A document carrying a secret is refused, not redacted** (FR-015). Redaction is
right for evidence, which arrives from a system nobody controls and has to be
usable anyway. A knowledge document is *authored*: a credential in one is a
mistake somebody can fix at the source, and storing it redacted would leave a
runbook with a hole in it that nobody knows about, permanently, while the
credential stays wherever it was pasted from. So the refusal names the rule, the
section, and the line — and never the matched text, because a refusal that echoed
the secret would put it in the trace, the log, and the console.

The refusal stands even when the guardrail engine is in audit-only mode, which is
the one place this package deviates from the ablation's usual "nothing is
blocked" rule. That ablation exists to measure the effect of guardrails on
investigation quality, and it is reversible run to run; a corpus that permanently
holds a credential is not a measurement artefact, and no experiment is worth it.

**Re-ingestion supersedes** (FR-011's other half). Chunks are replaced wholesale
rather than merged, because a runbook whose middle section was deleted would
otherwise leave that section in the index forever — retrievable, confident, and
describing a procedure that no longer exists. A document whose checksum has not
moved is skipped entirely, which is what makes a nightly sync of a hundred
runbooks cost the two that changed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from config.constants.knowledge import MAX_DOCUMENT_CHUNKS
from config.constants.persistence import KNOWLEDGE_VECTOR_NAMESPACE
from platform.guardrails.engine import GuardrailEngine, ScanResult
from platform.knowledge.base.chunking import TextChunk, chunk_document, line_at, section_at
from platform.knowledge.base.models import Chunk, Document
from platform.knowledge.clock import now as _utc_now
from platform.memory.embeddings.port import Embedder
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork
from platform.persistence.ports.vector_index import VectorRecord

logger = get_logger(__name__)

#: How a chunk id is built. Derived from the document and the ordinal rather than
#: generated, so re-ingesting a document produces the same ids for the parts that
#: did not move — which is what makes a diff of two ingestions readable.
CHUNK_ID = "{document_id}#{ordinal:04d}"


class IngestionOutcome(StrEnum):
    """What happened to a document offered for ingestion."""

    #: Chunked, embedded, and searchable.
    STORED = "stored"

    #: Already present with the same checksum. Nothing was re-embedded.
    UNCHANGED = "unchanged"

    #: Refused at the boundary. Nothing was written.
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SecretLocation:
    """Where a detected secret is, in the terms somebody would go looking.

    Carries no text. The rule name says what kind of thing matched, the section
    and line say where to look, and the offsets let a console highlight it
    locally — none of which reproduces the secret.
    """

    rule: str
    section: str
    line: int
    start: int
    end: int

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this location."""
        return {
            "rule": self.rule,
            "section": self.section,
            "line": self.line,
            "start": self.start,
            "end": self.end,
        }

    def describe(self) -> str:
        """Return the one-line form an operator reads."""
        where = f"section {self.section!r}, " if self.section else ""
        return f"{self.rule} at {where}line {self.line}"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What one ingestion did, and why, when it did nothing."""

    document: Document
    outcome: IngestionOutcome
    chunks: int = 0
    locations: tuple[SecretLocation, ...] = ()
    rules_fired: tuple[str, ...] = ()
    reason: str = ""
    superseded: bool = False

    @property
    def rejected(self) -> bool:
        """Return whether the document was refused at the boundary."""
        return self.outcome is IngestionOutcome.REJECTED

    @property
    def stored(self) -> bool:
        """Return whether anything was written."""
        return self.outcome is IngestionOutcome.STORED

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record a sync run or an audit keeps."""
        return {
            "document_id": self.document.document_id,
            "outcome": self.outcome.value,
            "version": self.document.version,
            "chunks": self.chunks,
            "superseded": self.superseded,
            "rules_fired": list(self.rules_fired),
            "locations": [location.to_record() for location in self.locations],
            "reason": self.reason,
        }


def secret_locations(body: str, scan: ScanResult) -> tuple[SecretLocation, ...]:
    """Return where each detected secret sits, without quoting any of it.

    Merged spans rather than raw matches, so a connection string whose password
    also matched the generic-secret rule is reported once, at the place a reader
    would go and look.
    """
    return tuple(
        SecretLocation(
            rule=span.rule,
            section=section_at(body, span.start).title,
            line=line_at(body, span.start),
            start=span.start,
            end=span.end,
        )
        for span in scan.spans
    )


def rejection_reason(locations: Sequence[SecretLocation]) -> str:
    """Return the sentence a refused ingestion reports.

    Names the rules and the places; never the match. Repeating the text back
    would put the secret in the trace the refusal was keeping it out of.
    """
    listed = "; ".join(location.describe() for location in locations)
    return (
        f"This document was not ingested because the guardrail engine detected credential "
        f"material in it: {listed}. The matched text is not reproduced here. Remove the "
        f"credential from the source document, rotate it, and ingest again."
    )


@dataclass(slots=True)
class KnowledgeIngestor:
    """Screening, chunking, embedding, and storage for one team's documents."""

    gateway: PersistenceGateway
    scope: TenantScope
    embedder: Embedder
    engine: GuardrailEngine | None = None
    clock: Callable[[], datetime] = _utc_now
    #: Namespaces this ingestor has already declared, so a run of two hundred
    #: documents does not re-declare the index two hundred times.
    _declared: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: ingestion must be scoped to a team — an unscoped "
                "document is one every team can retrieve"
            )

    async def ingest(self, document: Document) -> IngestionResult:
        """Screen, chunk, embed, and store ``document``, or say why not.

        Three outcomes, and the caller's next move differs for each: stored is
        done, unchanged means the source has not moved since the last sync, and
        rejected is a message for whoever wrote the document.
        """
        self._require_own_team(document)
        scan = self._screen(document)
        if scan is not None and not scan.clean:
            locations = secret_locations(document.body, scan)
            reason = rejection_reason(locations)
            logger.warning(
                "knowledge.document_rejected",
                document=document.document_id,
                rules=list(scan.rules_fired),
                locations=[location.describe() for location in locations],
            )
            return IngestionResult(
                document=document,
                outcome=IngestionOutcome.REJECTED,
                locations=locations,
                rules_fired=scan.rules_fired,
                reason=reason,
            )

        passages = chunk_document(document.body)
        if len(passages) > MAX_DOCUMENT_CHUNKS:
            reason = (
                f"This document produces {len(passages)} chunks, above the "
                f"{MAX_DOCUMENT_CHUNKS} one document may hold. Split it into the sections a "
                f"reader would actually follow, and ingest those."
            )
            logger.warning(
                "knowledge.document_too_large",
                document=document.document_id,
                chunks=len(passages),
            )
            return IngestionResult(
                document=document, outcome=IngestionOutcome.REJECTED, reason=reason
            )

        await self._ensure_index()
        embeddings = await self.embedder.embed([chunk.embedding_text() for chunk in passages])

        async with self.gateway.begin(self.scope) as uow:
            existing = await uow.knowledge.get_document(document.document_id)
            if existing is not None and existing.checksum == document.checksum:
                logger.info("knowledge.document_unchanged", document=document.document_id)
                return IngestionResult(
                    document=document, outcome=IngestionOutcome.UNCHANGED, chunks=len(passages)
                )

            superseded = existing is not None
            version = int(existing.metadata.get("version", 0)) + 1 if existing else 1
            stamped = replace(
                document, version=version, updated_at=document.updated_at or self.clock()
            )

            await uow.knowledge.upsert_document(stamped.to_stored())
            await self._replace_chunks(uow, stamped, passages, embeddings)

        logger.info(
            "knowledge.document_ingested",
            document=stamped.document_id,
            version=stamped.version,
            chunks=len(passages),
            superseded=superseded,
        )
        return IngestionResult(
            document=stamped,
            outcome=IngestionOutcome.STORED,
            chunks=len(passages),
            superseded=superseded,
        )

    async def delete(self, document_id: str) -> bool:
        """Delete a document, its chunks, and their vectors. Return whether it existed.

        The vectors go in the same unit of work. A chunk deleted from the store
        whose vector survives is a search result that resolves to nothing — which
        retrieval handles, but only by dropping a result the caller was told
        existed.
        """
        async with self.gateway.begin(self.scope) as uow:
            document = await uow.knowledge.get_document(document_id)
            if document is None:
                return False
            chunks = await uow.knowledge.chunks_for_document(document_id)
            await uow.vectors.delete(
                KNOWLEDGE_VECTOR_NAMESPACE, [chunk.chunk_id for chunk in chunks]
            )
            removed = await uow.knowledge.delete_document(document_id)

        logger.info("knowledge.document_deleted", document=document_id, chunks=len(chunks))
        return removed

    # -- internals -------------------------------------------------------------

    def _require_own_team(self, document: Document) -> None:
        """Raise unless ``document`` belongs to the team this ingestor writes for."""
        if document.team_node_id != self.scope.team_node_id:
            raise ValueError(
                f"{document.document_id}: this ingestor writes for team "
                f"{self.scope.team_node_id!r} and the document declares "
                f"{document.team_node_id!r} — a document written under the wrong team is "
                f"one the wrong team can search"
            )

    def _screen(self, document: Document) -> ScanResult | None:
        """Return what the guardrail engine found, or ``None`` when it is absent.

        The title is scanned with the body. A credential in a document's *title*
        is rarer and worse — it reaches every listing, every search result, and
        the review queue, none of which show the body.
        """
        if self.engine is None:
            return None
        return self.engine.scan(f"{document.title}\n{document.body}")

    async def _ensure_index(self) -> None:
        """Declare the knowledge namespace at this embedder's model and width."""
        if self._declared:
            return
        async with self.gateway.begin(self.scope) as uow:
            await uow.vectors.ensure(
                KNOWLEDGE_VECTOR_NAMESPACE,
                model=self.embedder.model,
                dimension=self.embedder.dimension,
            )
        self._declared = True

    async def _replace_chunks(
        self,
        uow: UnitOfWork,
        document: Document,
        passages: Sequence[TextChunk],
        embeddings: Sequence[tuple[float, ...]],
    ) -> None:
        """Make ``passages`` the document's whole chunk set, vectors included.

        The old vectors are deleted before the new ones are written, in the same
        unit of work. A document that shrank from twelve chunks to eight would
        otherwise leave four vectors pointing at chunk ids the store no longer
        holds.
        """
        previous = await uow.knowledge.chunks_for_document(document.document_id)
        if previous:
            await uow.vectors.delete(
                KNOWLEDGE_VECTOR_NAMESPACE, [chunk.chunk_id for chunk in previous]
            )

        chunks = [
            Chunk(
                chunk_id=CHUNK_ID.format(document_id=document.document_id, ordinal=passage.ordinal),
                document_id=document.document_id,
                ordinal=passage.ordinal,
                text=passage.text,
                section=passage.section,
                start=passage.start,
                end=passage.end,
            )
            for passage in passages
        ]

        await uow.knowledge.replace_chunks(
            document.document_id, [chunk.to_stored() for chunk in chunks]
        )
        await uow.vectors.upsert(
            KNOWLEDGE_VECTOR_NAMESPACE,
            [
                VectorRecord(
                    vector_id=chunk.chunk_id,
                    embedding=tuple(embedding),
                    metadata=chunk.vector_metadata(document),
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ],
        )


__all__ = [
    "CHUNK_ID",
    "IngestionOutcome",
    "IngestionResult",
    "KnowledgeIngestor",
    "SecretLocation",
    "rejection_reason",
    "secret_locations",
]
