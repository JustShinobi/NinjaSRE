"""Searching a real corpus for a symptom, and telling the two answers apart.

The fixture holds the same failure written down twice: an entry that records the
symptom and never found the cause, and one three days later that found it. A
search for the symptom returns both, because both are about it — and an agent
handed the two with nothing to choose between them will follow whichever the
embedding happened to rank first, which is the entry that concluded nothing
about half the time.

So the corpus's own answer travels with the result. A post-mortem that names a
cause says so in the shape the caller reads, and the two are ordered against
each other rather than left to the similarity score.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.postmortem import PostmortemExtractor
from platform.knowledge.base.search import KnowledgeQuery, KnowledgeResult, KnowledgeSearch
from platform.knowledge.base.sync.corpus import SOURCE, CorpusSource
from platform.knowledge.base.sync.port import KnowledgeSync, document_id_for
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"

JULY_17 = document_id_for(SOURCE, "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md")
JULY_20 = document_id_for(SOURCE, "docs/postmortem/2026-07-20-adguard-dns-recurrence-memcg-oom.md")
RECOVERY = document_id_for(SOURCE, "docs/runbooks/adguard-dns-recovery.md")

#: What somebody types when the resolvers stop answering.
SYMPTOM = "AdGuard DNS stopped answering queries on both instances"


@pytest.fixture
async def searcher(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> KnowledgeSearch:
    """Return a search over the whole fixture corpus, ingested."""
    await KnowledgeSync(
        ingestor=KnowledgeIngestor(
            gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
        ),
        scope=scope,
        clock=clock,
    ).run(CorpusSource(root=CORPUS, extractor=PostmortemExtractor(llm=None)))
    return KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)


@pytest.fixture
async def found(searcher: KnowledgeSearch) -> KnowledgeResult:
    """Return what a search for the symptom returned."""
    return await searcher.search(KnowledgeQuery(text=SYMPTOM, limit=10))


class TestSearchingForTheSymptom:
    """Both entries and the procedure, which is what somebody asking needs."""

    def test_both_postmortems_and_the_recovery_runbook_come_back(
        self, found: KnowledgeResult
    ) -> None:
        assert {JULY_17, JULY_20, RECOVERY} <= set(found.documents)

    def test_the_entry_that_carries_the_cause_is_named_as_such(
        self, found: KnowledgeResult
    ) -> None:
        # Both are returned; only one of them concluded anything, and it is the
        # difference between the two that the result has to make visible.
        assert JULY_20 in found.explaining
        assert JULY_17 not in found.explaining

    def test_the_entry_that_carries_the_cause_is_ranked_above_the_one_that_does_not(
        self, found: KnowledgeResult
    ) -> None:
        postmortems = [
            entry.document_id
            for entry in found.chunks
            if entry.citation.document_type is DocumentType.POSTMORTEM
        ]

        assert postmortems.index(JULY_20) < postmortems.index(JULY_17)

    def test_a_returned_postmortem_carries_the_fields_the_corpus_extracted(
        self, found: KnowledgeResult
    ) -> None:
        explaining = next(entry for entry in found.chunks if entry.document_id == JULY_20)

        assert explaining.postmortem is not None
        assert explaining.explains
        assert "memory cgroup" in explaining.postmortem.root_cause
        assert explaining.postmortem.recurrence_of == (
            "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md"
        )

    def test_the_entry_that_found_nothing_says_so_rather_than_carrying_nothing(
        self, found: KnowledgeResult
    ) -> None:
        earlier = next(entry for entry in found.chunks if entry.document_id == JULY_17)

        assert earlier.postmortem is not None
        assert earlier.postmortem.symptom
        assert not earlier.explains

    def test_a_runbook_carries_no_postmortem_fields(self, found: KnowledgeResult) -> None:
        runbook = next(entry for entry in found.chunks if entry.document_id == RECOVERY)

        assert runbook.postmortem is None
        assert not runbook.explains

    def test_every_result_still_cites_the_section_it_came_from(
        self, found: KnowledgeResult
    ) -> None:
        assert all(entry.citation.location for entry in found.chunks)


class TestTheRankingIsNarrow:
    """It reorders post-mortems against each other and nothing else."""

    async def test_a_search_that_returns_no_postmortem_is_left_exactly_as_it_was(
        self, searcher: KnowledgeSearch
    ) -> None:
        query = KnowledgeQuery(text="overlay zone MTU", document_type="runbook", limit=5)

        result = await searcher.search(query)

        assert result.chunks
        assert list(result.chunks) == sorted(result.chunks, key=lambda entry: -entry.score), (
            "similarity order must survive when nothing is reordered"
        )

    async def test_the_same_query_twice_returns_the_same_order(
        self, searcher: KnowledgeSearch
    ) -> None:
        first = await searcher.search(KnowledgeQuery(text=SYMPTOM, limit=10))
        second = await searcher.search(KnowledgeQuery(text=SYMPTOM, limit=10))

        assert [entry.chunk.chunk_id for entry in first.chunks] == [
            entry.chunk.chunk_id for entry in second.chunks
        ]
