"""What a sync source is, and how a run of one reports what it did.

Four adapters ship and they read four completely different shapes, so the port is
the narrow thing they agree on: a source has a name and can be asked for
documents. Everything vendor-specific — how a page's body is stored, where its
parent is recorded, what its URL looks like — belongs to the adapter, because
that is the part that is different, and pushing any of it up here would mean the
next source has to fit a shape derived from Confluence.

**Document ids are namespaced by the source.** A Confluence page and a Notion
page can carry the same identifier, and a corpus where one silently superseded
the other would lose a document with no error anywhere. The namespacing happens
in ``KnowledgeSync`` rather than in each adapter, so an adapter cannot forget.

**A sync run reports per document.** One page whose author pasted a credential
into it must not fail the other ninety-nine, and it must not disappear either:
the report names it, with the location the ingestion boundary found, so somebody
can fix the source page. A run that returned a single "failed" would be a run
nobody can act on.

**No vendor client is imported here or in the adapters.** ``platform`` is tier 3
and the integrations are tier 2, so each adapter takes a *reader* over whatever
the deployment already has. That is also what makes them testable without a wiki.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.knowledge import MAX_SYNC_DOCUMENTS_PER_RUN
from platform.knowledge.base.ingestion import IngestionOutcome, IngestionResult, KnowledgeIngestor
from platform.knowledge.base.models import Document, DocumentOrigin, DocumentType
from platform.knowledge.clock import now as _utc_now
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)

#: How a synced document's id is built. The source name leads, so two sources
#: that use the same external identifier produce two documents rather than one
#: silently superseding the other.
SYNCED_DOCUMENT_ID = "{source}:{external_id}"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One document as a sync source found it, before it is a Document."""

    external_id: str
    title: str
    body: str
    source_uri: str = ""
    document_type: DocumentType = DocumentType.RUNBOOK
    parent_external_id: str = ""
    updated_at: datetime | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.external_id.strip():
            raise ValueError("a source document must carry the identifier its source knows it by")


@runtime_checkable
class DocumentSource(Protocol):
    """Something that can list documents from a system the operator already runs."""

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the documents this source is scoped to, most recent first."""


@dataclass(frozen=True, slots=True)
class SyncReport:
    """What one sync run did, per document.

    ``rejected`` is a list rather than a count on purpose. Each entry is a page
    somebody has to go and edit, and a report that said "three rejected" would be
    a report nobody can act on.
    """

    source: str
    at: datetime
    stored: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    truncated: bool = False

    @property
    def total(self) -> int:
        """Return how many documents this run looked at."""
        return len(self.stored) + len(self.unchanged) + len(self.rejected)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record a scheduled run logs."""
        return {
            "source": self.source,
            "at": self.at.isoformat(),
            "stored": list(self.stored),
            "unchanged": list(self.unchanged),
            "rejected": [
                {"document_id": document_id, "reason": reason}
                for document_id, reason in self.rejected
            ],
            "truncated": self.truncated,
        }


@dataclass(slots=True)
class KnowledgeSync:
    """Runs a document source into one team's knowledge base."""

    ingestor: KnowledgeIngestor
    scope: TenantScope
    clock: Callable[[], datetime] = _utc_now
    #: Documents one run may ingest. A first sync against a large wiki lands in
    #: several runs rather than one that holds a transaction open for an hour.
    limit: int = MAX_SYNC_DOCUMENTS_PER_RUN
    _tree: dict[str, str] = field(default_factory=dict, init=False)

    async def run(self, source: DocumentSource) -> SyncReport:
        """Fetch from ``source`` and ingest what it returned, one document at a time.

        One document's failure never stops the run. A page whose author pasted a
        credential into it is a page somebody has to edit, and failing the other
        ninety-nine because of it would mean a corpus that never syncs until
        somebody notices.
        """
        moment = self.clock()
        found = await source.fetch()
        truncated = len(found) > self.limit

        stored: list[str] = []
        unchanged: list[str] = []
        rejected: list[tuple[str, str]] = []

        for entry in found[: self.limit]:
            result = await self._ingest(source, entry, at=moment)
            document_id = result.document.document_id
            if result.outcome is IngestionOutcome.STORED:
                stored.append(document_id)
            elif result.outcome is IngestionOutcome.UNCHANGED:
                unchanged.append(document_id)
            else:
                rejected.append((document_id, result.reason))

        report = SyncReport(
            source=source.name,
            at=moment,
            stored=tuple(stored),
            unchanged=tuple(unchanged),
            rejected=tuple(rejected),
            truncated=truncated,
        )
        logger.info("knowledge.sync_completed", **report.to_record())
        return report

    async def _ingest(
        self, source: DocumentSource, entry: SourceDocument, *, at: datetime
    ) -> IngestionResult:
        """Turn one source document into a ``Document`` and ingest it."""
        return await self.ingestor.ingest(
            Document(
                document_id=document_id_for(source.name, entry.external_id),
                org_id=self.scope.org_id,
                team_node_id=self.scope.team_node_id or "",
                title=entry.title or entry.external_id,
                body=entry.body,
                document_type=entry.document_type,
                origin=DocumentOrigin.SYNC,
                source_uri=entry.source_uri,
                parent_id=(
                    document_id_for(source.name, entry.parent_external_id)
                    if entry.parent_external_id
                    else ""
                ),
                tags=entry.tags,
                updated_at=entry.updated_at or at,
            )
        )


def document_id_for(source: str, external_id: str) -> str:
    """Return the namespaced document id one source's identifier maps to."""
    return SYNCED_DOCUMENT_ID.format(source=source, external_id=external_id)


__all__ = [
    "SYNCED_DOCUMENT_ID",
    "DocumentSource",
    "KnowledgeSync",
    "SourceDocument",
    "SyncReport",
    "document_id_for",
]
