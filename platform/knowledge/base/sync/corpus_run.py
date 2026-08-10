"""One pass over a repository's documentation, and everything it produces.

Four things come out of a corpus and each has its own module; this is the one
place they happen in order, because the order is load-bearing:

1. **Ingest**, through the ordinary sync. Screening, chunking, the chunk limit,
   idempotence and versioning are all inherited rather than reimplemented — a
   document carrying a credential is refused here exactly as one from a wiki is.
2. **Link to the estate**, from what was ingested. A document refused at the
   boundary must not reach the graph, which is why this is second and reads the
   run's own report rather than the source's output.
3. **Read the verification document**, into candidate detectors nobody has
   enabled. Proposals, returned rather than written: the configuration service
   owns detector writes, with the audit line and the approval gate in front.
4. **Report the degradations**, so a deployment with no extraction model looks
   degraded rather than looking like a corpus of post-mortems that established
   nothing.

The report is the whole return value. A sync that logged what it did and
returned a count would be one nobody can act on, and every entry here is
something somebody eventually has to look at: a file that was refused, a
document that lost its fields, a check waiting for a decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from platform.knowledge.base.detector_candidates import DetectorCandidate, candidates_from
from platform.knowledge.base.estate_links import EstateLinker, LinkReport
from platform.knowledge.base.models import Document, DocumentOrigin
from platform.knowledge.base.sync.corpus import CorpusSource
from platform.knowledge.base.sync.port import KnowledgeSync, SyncReport, document_id_for
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """What one pass over a repository's documentation did, in full."""

    sync: SyncReport
    links: LinkReport = field(default_factory=LinkReport)
    #: Detectors the verification documents propose. Returned, never written:
    #: writing a detector is a configuration change and the configuration
    #: service owns those.
    candidates: tuple[DetectorCandidate, ...] = ()
    #: Files the source's own bounds put out of reach, as ``(path, reason)``.
    skipped: tuple[tuple[str, str], ...] = ()
    #: One sentence per post-mortem that wanted the extraction model and did not
    #: get it. Named rather than silent — see the extractor.
    degradations: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record a scheduled run logs."""
        return {
            **self.sync.to_record(),
            "linked": self.links.linked,
            "links_removed": self.links.removed,
            "links_unavailable": self.links.unavailable,
            "candidates": [candidate.detector_id for candidate in self.candidates],
            "skipped": [{"path": path, "reason": reason} for path, reason in self.skipped],
            "degradations": list(self.degradations),
        }


@dataclass(slots=True)
class CorpusSync:
    """Runs one repository's documentation into everything it feeds."""

    ingestor_sync: KnowledgeSync
    gateway: PersistenceGateway
    scope: TenantScope

    async def run(self, source: CorpusSource) -> CorpusReport:
        """Ingest ``source``, join it to the estate, and report what it proposes."""
        found = await source.fetch()
        report = await self.ingestor_sync.run(source)

        stored = set(report.stored) | set(report.unchanged)
        documents = [
            self._document(source, entry)
            for entry in found
            if document_id_for(source.name, entry.external_id) in stored
        ]

        links = await EstateLinker(gateway=self.gateway, scope=self.scope).link(documents)
        candidates = tuple(
            candidate
            for document in documents
            for candidate in candidates_from(
                document.body,
                document_id=document.document_id,
                location=document.location,
            )
        )

        result = CorpusReport(
            sync=report,
            links=links,
            candidates=candidates,
            skipped=tuple(source.skipped),
            degradations=(source.extractor.degradations if source.extractor is not None else ()),
        )
        logger.info("knowledge.corpus_synced", **result.to_record())
        return result

    def _document(self, source: CorpusSource, entry: Any) -> Document:
        """Return one fetched entry as the document the store now holds.

        Rebuilt rather than read back. The body is what the linker and the
        candidate reader work over, and the store keeps chunks rather than a
        body — so reading it back would mean reassembling the text from its
        overlapping passages.
        """
        return Document(
            document_id=document_id_for(source.name, entry.external_id),
            org_id=self.scope.org_id,
            team_node_id=self.scope.team_node_id or "",
            title=entry.title or entry.external_id,
            body=entry.body,
            document_type=entry.document_type,
            origin=DocumentOrigin.SYNC,
            source_uri=entry.source_uri,
            tags=entry.tags,
            updated_at=entry.updated_at,
            metadata=entry.metadata,
        )


def settings_patch(candidates: Sequence[DetectorCandidate]) -> dict[str, Any]:
    """Return the configuration patch that would add ``candidates`` as detectors.

    A patch rather than a write, for the reason the detector toggle is one: the
    configuration service owns detector writes, including the audit line, the
    field locks and the approval gate. A sync that wrote around it would be a
    document changing what a deployment watches with no record of who agreed.
    """
    return {
        "policies": {
            "observation": {"detectors": [candidate.to_settings() for candidate in candidates]}
        }
    }


__all__ = ["CorpusReport", "CorpusSync", "settings_patch"]
