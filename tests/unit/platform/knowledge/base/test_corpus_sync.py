"""Syncing a repository's documentation, twice, and what changes between them.

Three properties, and the third is the one that decides whether a nightly sync
is worth running at all.

**A document carrying a credential is refused by name and never by value.** The
fixture holds a runbook with a connection string and a private key in it. The
run has to name the file, name the rules, and put neither string in the report,
the log, or the stored corpus.

**Re-syncing an unchanged tree writes nothing.** A hundred runbooks that have
not moved cost a hundred checksum comparisons, not a hundred embedding passes.

**Change is decided by content, never by the clock.** A rewritten runbook is a
new version; ``touch`` is nothing at all.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import Document, DocumentType
from platform.knowledge.base.sync.corpus import SOURCE, CorpusSource
from platform.knowledge.base.sync.port import KnowledgeSync, SyncReport, document_id_for
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"

#: The runbook the fixture deliberately spoils, and the two values in it. Both
#: are invented; both match a shipped rule.
LEAKY = "docs/runbooks/backup-restore.md"
CONNECTION_STRING_PASSWORD = "hunter2correcthorsebattery"
PRIVATE_KEY_BODY = "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ"

#: Every document the fixture corpus stores. The refused runbook is not here.
STORED_DOCUMENTS = 19


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """Return a writable copy of the fixture corpus.

    Copied rather than read in place, because two of these tests edit a document
    and one changes a modification time.
    """
    root = tmp_path / "infra"
    shutil.copytree(CORPUS, root)
    return root


def syncer(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> KnowledgeSync:
    """Return a sync runner over a real ingestor and the shipped ruleset."""
    return KnowledgeSync(
        ingestor=KnowledgeIngestor(
            gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
        ),
        scope=scope,
        clock=clock,
    )


async def _stored(gateway: PersistenceGateway, scope: TenantScope, external_id: str) -> Document:
    """Return one synced document as the store now holds it."""
    async with gateway.begin(scope) as uow:
        record = await uow.knowledge.get_document(document_id_for(SOURCE, external_id))
    assert record is not None, external_id
    return Document.from_stored(record, org_id=scope.org_id)


async def _every_chunk(gateway: PersistenceGateway, scope: TenantScope) -> str:
    """Return every stored passage of every synced document, concatenated."""
    text: list[str] = []
    async with gateway.begin(scope) as uow:
        for document in await uow.knowledge.list_documents():
            for chunk in await uow.knowledge.chunks_for_document(document.document_id):
                text.append(chunk.text)
    return "\n".join(text)


class TestOneRunOverTheWholeCorpus:
    """What a first sync of a repository's documentation does."""

    async def test_every_allowed_document_is_stored_with_its_derived_type(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        report = await syncer(gateway, scope, embedder, engine, clock).run(
            CorpusSource(root=corpus)
        )

        assert len(report.stored) == STORED_DOCUMENTS
        assert report.unchanged == ()
        assert not report.truncated

        by_type: dict[DocumentType, int] = {}
        for document_id in report.stored:
            external = document_id.removeprefix(f"{SOURCE}:")
            document = await _stored(gateway, scope, external)
            by_type[document.document_type] = by_type.get(document.document_type, 0) + 1

        assert by_type == {
            DocumentType.RUNBOOK: 3,
            DocumentType.POSTMORTEM: 10,
            DocumentType.ARCHITECTURE: 3,
            DocumentType.REFERENCE: 1,
            DocumentType.POLICY: 2,
        }

    async def test_a_stored_document_cites_the_path_an_operator_can_open(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        await syncer(gateway, scope, embedder, engine, clock).run(CorpusSource(root=corpus))

        document = await _stored(gateway, scope, "docs/runbooks/adguard-dns-recovery.md")

        assert document.source_uri == "docs/runbooks/adguard-dns-recovery.md"
        assert document.location == "docs/runbooks/adguard-dns-recovery.md"
        assert document.title == "Recovering AdGuard DNS"


class TestTheDocumentCarryingACredential:
    """Refused by name, and by nothing else."""

    @pytest.fixture
    async def run(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> SyncReport:
        with caplog.at_level(logging.DEBUG):
            return await syncer(gateway, scope, embedder, engine, clock).run(
                CorpusSource(root=corpus)
            )

    async def test_it_is_refused_and_the_report_names_the_file(self, run: SyncReport) -> None:
        assert [document_id for document_id, _ in run.rejected] == [document_id_for(SOURCE, LEAKY)]

    async def test_the_reason_names_the_rules_that_fired(self, run: SyncReport) -> None:
        reason = run.rejected[0][1]

        assert "private-key-block" in reason
        assert "database-connection-string" in reason

    async def test_the_value_is_in_neither_half_of_the_report(self, run: SyncReport) -> None:
        rendered = str(run.to_record())

        assert CONNECTION_STRING_PASSWORD not in rendered
        assert PRIVATE_KEY_BODY not in rendered

    async def test_the_value_reaches_no_log_line(
        self, run: SyncReport, caplog: pytest.LogCaptureFixture
    ) -> None:
        assert run.rejected, "the fixture must actually be refused"
        logged = "\n".join(record.getMessage() for record in caplog.records)

        assert CONNECTION_STRING_PASSWORD not in logged
        assert PRIVATE_KEY_BODY not in logged

    async def test_no_passage_of_it_was_stored(
        self, run: SyncReport, gateway: PersistenceGateway, scope: TenantScope
    ) -> None:
        assert run.rejected, "the fixture must actually be refused"
        corpus_text = await _every_chunk(gateway, scope)

        assert CONNECTION_STRING_PASSWORD not in corpus_text
        assert PRIVATE_KEY_BODY not in corpus_text

    async def test_the_document_itself_was_never_written(
        self, run: SyncReport, gateway: PersistenceGateway, scope: TenantScope
    ) -> None:
        assert run.rejected, "the fixture must actually be refused"
        async with gateway.begin(scope) as uow:
            assert await uow.knowledge.get_document(document_id_for(SOURCE, LEAKY)) is None


class TestReSyncing:
    """Content decides, and the clock does not."""

    async def test_a_second_run_of_an_unchanged_tree_stores_nothing(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        run = syncer(gateway, scope, embedder, engine, clock)
        await run.run(CorpusSource(root=corpus))

        again = await run.run(CorpusSource(root=corpus))

        assert again.stored == ()
        assert len(again.unchanged) == STORED_DOCUMENTS

    async def test_touching_every_file_changes_nothing(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        run = syncer(gateway, scope, embedder, engine, clock)
        await run.run(CorpusSource(root=corpus))

        for path in sorted(corpus.rglob("*.md")):
            # A modification time far in the future, and a byte-identical body.
            os.utime(path, (2_000_000_000, 2_000_000_000))

        again = await run.run(CorpusSource(root=corpus))

        assert again.stored == ()
        assert len(again.unchanged) == STORED_DOCUMENTS

    async def test_an_edited_body_supersedes_to_the_next_version_and_nothing_else_moves(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        run = syncer(gateway, scope, embedder, engine, clock)
        await run.run(CorpusSource(root=corpus))
        edited = "docs/runbooks/vxlan-zone-mtu.md"
        path = corpus / edited
        path.write_text(
            path.read_text(encoding="utf-8") + "\n## Afterwards\n\nRe-check the overlay.\n",
            encoding="utf-8",
        )

        again = await run.run(CorpusSource(root=corpus))

        assert again.stored == (document_id_for(SOURCE, edited),)
        assert len(again.unchanged) == STORED_DOCUMENTS - 1
        assert (await _stored(gateway, scope, edited)).version == 2

    async def test_a_document_removed_from_the_corpus_is_simply_not_in_the_next_report(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
    ) -> None:
        run = syncer(gateway, scope, embedder, engine, clock)
        await run.run(CorpusSource(root=corpus))
        (corpus / "docs/analysis/capacity-review-2026-q2.md").unlink()

        again = await run.run(CorpusSource(root=corpus))

        assert document_id_for(SOURCE, "docs/analysis/capacity-review-2026-q2.md") not in (
            again.unchanged + again.stored
        )
        assert len(again.unchanged) == STORED_DOCUMENTS - 1
