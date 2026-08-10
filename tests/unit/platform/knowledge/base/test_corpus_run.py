"""One pass over the whole fixture corpus, and everything that falls out of it.

The four halves are tested apart; this is the assertion that they happen in the
right order and that the report a scheduled run leaves behind is one somebody
can act on. The order that matters most: a document refused at the ingestion
boundary must not reach the graph, so the link pass reads the sync's own report
rather than the source's output.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.detector_candidates import CANDIDATE_ID_PREFIX
from platform.knowledge.base.estate_links import HOST_LABEL_PREFIX, EstateLinker
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.postmortem import PostmortemExtractor
from platform.knowledge.base.sync.corpus import SOURCE, CorpusSource
from platform.knowledge.base.sync.corpus_run import CorpusReport, CorpusSync, settings_patch
from platform.knowledge.base.sync.port import KnowledgeSync, document_id_for
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.estate_repository import Resource
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"
LEAKY = document_id_for(SOURCE, "docs/runbooks/backup-restore.md")
HOSTNAME = "adguard.example.invalid"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "infra"
    shutil.copytree(CORPUS, root)
    return root


@pytest.fixture
async def estate(gateway: PersistenceGateway, scope: TenantScope) -> None:
    """Seed the one resource the fixture's documents name."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="proxmox:lxc/115",
                kind="container",
                source="proxmox",
                native_id="lxc/115",
                display_name="adguard",
                labels=(f"{HOST_LABEL_PREFIX}{HOSTNAME}",),
                last_seen_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )


@pytest.fixture
async def report(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
    corpus: Path,
    estate: None,
) -> CorpusReport:
    """Return what one pass over the fixture corpus produced."""
    run = CorpusSync(
        ingestor_sync=KnowledgeSync(
            ingestor=KnowledgeIngestor(
                gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
            ),
            scope=scope,
            clock=clock,
        ),
        gateway=gateway,
        scope=scope,
    )
    return await run.run(CorpusSource(root=corpus, extractor=PostmortemExtractor(llm=None)))


class TestOnePass:
    """Ingest, link, propose, and say what degraded."""

    def test_it_ingests_the_corpus_and_refuses_the_one_that_leaks(
        self, report: CorpusReport
    ) -> None:
        assert len(report.sync.stored) == 19
        assert [document_id for document_id, _ in report.sync.rejected] == [LEAKY]

    def test_it_links_the_resource_the_documents_name(self, report: CorpusReport) -> None:
        assert report.links.linked > 0
        assert report.links.unavailable == ""

    def test_it_proposes_the_verification_documents_checks(self, report: CorpusReport) -> None:
        assert [candidate.detector_id for candidate in report.candidates] == [
            f"{CANDIDATE_ID_PREFIX}quorum-margin-is-above-zero",
            f"{CANDIDATE_ID_PREFIX}no-datastore-is-above-its-safe-fill",
            f"{CANDIDATE_ID_PREFIX}no-backup-is-older-than-its-schedule",
            f"{CANDIDATE_ID_PREFIX}no-node-is-reporting-failed-units",
            f"{CANDIDATE_ID_PREFIX}no-mount-is-stalled",
        ]

    def test_every_proposal_arrives_disabled(self, report: CorpusReport) -> None:
        assert all(candidate.to_settings()["enabled"] is False for candidate in report.candidates)

    def test_it_names_the_post_mortem_that_wanted_a_model_and_had_none(
        self, report: CorpusReport
    ) -> None:
        assert len(report.degradations) == 1
        assert "2025-11-08-a-mount-that-would-not-clear.md" in report.degradations[0]

    def test_the_record_carries_every_half_of_what_happened(self, report: CorpusReport) -> None:
        record = report.to_record()

        assert record["candidates"]
        assert record["degradations"]
        assert record["linked"] == report.links.linked
        assert record["rejected"][0]["document_id"] == LEAKY


class TestTheRefusedDocumentReachesNothing:
    """The order that matters: refused at the boundary means refused everywhere."""

    async def test_the_document_that_leaks_is_not_in_the_graph(
        self,
        report: CorpusReport,
        gateway: PersistenceGateway,
        scope: TenantScope,
    ) -> None:
        assert report.sync.rejected, "the fixture must actually be refused"
        linked = await EstateLinker(gateway=gateway, scope=scope).documents_for("proxmox:lxc/115")

        assert LEAKY not in {entry.document_id for entry in linked}


class TestWhatTheProposalsBecome:
    """A configuration patch, never a configuration write."""

    def test_the_patch_is_the_shape_the_configuration_service_takes(
        self, report: CorpusReport
    ) -> None:
        patch = settings_patch(report.candidates)

        entries = patch["policies"]["observation"]["detectors"]
        assert len(entries) == len(report.candidates)
        assert all(entry["enabled"] is False for entry in entries)
        assert all(entry["origin"].startswith(f"{SOURCE}:") for entry in entries)


class TestRunningItAgain:
    """A second pass over an unchanged tree changes nothing."""

    async def test_nothing_is_stored_and_the_graph_is_the_same(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        embedder: LocalEmbedder,
        engine: GuardrailEngine,
        clock: Clock,
        corpus: Path,
        estate: None,
    ) -> None:
        run = CorpusSync(
            ingestor_sync=KnowledgeSync(
                ingestor=KnowledgeIngestor(
                    gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
                ),
                scope=scope,
                clock=clock,
            ),
            gateway=gateway,
            scope=scope,
        )
        first = await run.run(CorpusSource(root=corpus, extractor=PostmortemExtractor(llm=None)))

        again = await run.run(CorpusSource(root=corpus, extractor=PostmortemExtractor(llm=None)))

        assert again.sync.stored == ()
        assert len(again.sync.unchanged) == len(first.sync.stored)
        assert (again.links.linked, again.links.removed) == (first.links.linked, 0)
        assert [entry.detector_id for entry in again.candidates] == [
            entry.detector_id for entry in first.candidates
        ]
