"""What comes back from a search, and what it is enough to do with.

SC-005 is the assertion that carries this module: a result has to be *citable*.
The agent's guidance tells it to name the document and quote the passage rather
than restating it as its own finding, and it can only do that if the document,
the section, and a resolvable location arrive with the text.

The rest is about what must not come back: another team's runbooks, six chunks of
one document, or an empty result dressed up as an unavailability.
"""

from __future__ import annotations

import pytest

from config.constants.knowledge import MAX_CHUNKS_PER_DOCUMENT, MAX_KNOWLEDGE_SEARCH_RESULTS
from config.prompts.knowledge import KNOWLEDGE_DISABLED
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import Document, DocumentType
from platform.knowledge.base.search import (
    KnowledgeQuery,
    KnowledgeSearch,
    bounded_limit,
)
from platform.knowledge.policy import KnowledgePolicy
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import PAYMENTS_TEAM, PRIMARY_ORG, SEARCH_TEAM, Clock

pytestmark = pytest.mark.unit

FAILOVER = """# Payments failover

## Replica lag

When the payments replica lag exceeds ten seconds the checkout service returns
502 responses and the connection pool saturates.

## Failing over

Promote the standby, then drain the primary's connection pool before restarting.
"""

INDEXING = """# Search index rebuild

Rebuild the search index when the document count drifts from the source of truth
by more than one percent.
"""


def runbook(
    document_id: str,
    body: str,
    *,
    team: str = PAYMENTS_TEAM,
    uri: str = "",
    document_type: DocumentType = DocumentType.RUNBOOK,
) -> Document:
    """Return a document for the payments team unless told otherwise."""
    return Document(
        document_id=document_id,
        org_id=PRIMARY_ORG,
        team_node_id=team,
        title=body.splitlines()[0].lstrip("# "),
        body=body,
        source_uri=uri,
        document_type=document_type,
    )


def ingestor(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> KnowledgeIngestor:
    """Return an ingestor for one team."""
    return KnowledgeIngestor(
        gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
    )


async def test_a_result_carries_its_document_section_and_a_resolvable_location(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """SC-005: the agent can cite rather than paraphrase."""
    await ingestor(gateway, scope, embedder, engine, clock).ingest(
        runbook("payments-failover", FAILOVER, uri="https://wiki.example/payments-failover")
    )
    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)

    result = await search.search(KnowledgeQuery(text="payments replica lag 502 connection pool"))

    assert not result.empty
    citation = result.chunks[0].citation
    assert citation.document_id == "payments-failover"
    assert citation.title == "Payments failover"
    assert citation.section.startswith("Payments failover")
    assert citation.location == "https://wiki.example/payments-failover"
    assert citation.reference.startswith("https://wiki.example/payments-failover#")


async def test_a_document_without_a_source_uri_still_has_a_location(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # A citation whose location is an empty string is a citation the reader
    # cannot check, which is the whole thing citations exist to prevent.
    await ingestor(gateway, scope, embedder, engine, clock).ingest(
        runbook("payments-failover", FAILOVER)
    )
    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)

    result = await search.search(KnowledgeQuery(text="replica lag"))

    assert result.chunks[0].citation.location == "knowledge:payments-failover"


async def test_one_document_cannot_own_the_whole_answer(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # A runbook repeating a phrase across six sections would otherwise win every
    # slot, and the answer stops being a search over the corpus.
    repetitive = "# Pool\n\n" + "\n\n".join(
        f"## Section {index}\n\nThe connection pool saturates under replica lag."
        for index in range(8)
    )
    await ingestor(gateway, scope, embedder, engine, clock).ingest(runbook("pool", repetitive))
    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)

    result = await search.search(KnowledgeQuery(text="connection pool saturates"))

    assert len(result.chunks) <= MAX_CHUNKS_PER_DOCUMENT


async def test_an_empty_corpus_is_an_empty_result_not_an_unavailability(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    clock: Clock,
) -> None:
    """The common case for the first weeks of any deployment."""
    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)

    result = await search.search(KnowledgeQuery(text="anything at all"))

    assert result.searched is True
    assert result.empty is True
    assert result.reason == ""


async def test_a_disabled_knowledge_base_says_so_rather_than_returning_nothing(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    clock: Clock,
) -> None:
    search = KnowledgeSearch(
        gateway=gateway,
        scope=scope,
        embedder=embedder,
        policy=KnowledgePolicy(knowledge_enabled=False),
        clock=clock,
    )

    result = await search.search(KnowledgeQuery(text="replica lag"))

    assert result.searched is False
    assert result.reason == KNOWLEDGE_DISABLED


async def test_a_team_cannot_search_another_teams_documents(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """FR-025, asserted from both sides."""
    await ingestor(gateway, scope, embedder, engine, clock).ingest(
        runbook("payments-failover", FAILOVER)
    )
    await ingestor(gateway, other_team_scope, embedder, engine, clock).ingest(
        runbook("index-rebuild", INDEXING, team=SEARCH_TEAM)
    )

    ours = await KnowledgeSearch(
        gateway=gateway, scope=scope, embedder=embedder, clock=clock
    ).search(KnowledgeQuery(text="rebuild the search index document count"))
    theirs = await KnowledgeSearch(
        gateway=gateway, scope=other_team_scope, embedder=embedder, clock=clock
    ).search(KnowledgeQuery(text="payments replica lag"))

    assert "index-rebuild" not in ours.documents
    assert "payments-failover" not in theirs.documents


async def test_a_document_type_filter_excludes_the_wrong_kind_of_document(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # An agent that wants a procedure and gets a post-mortem about the same
    # service has been given the wrong kind of document.
    writes = ingestor(gateway, scope, embedder, engine, clock)
    await writes.ingest(runbook("failover-runbook", FAILOVER))
    await writes.ingest(
        runbook("failover-postmortem", FAILOVER, document_type=DocumentType.POSTMORTEM)
    )

    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)
    result = await search.search(KnowledgeQuery(text="replica lag", document_type="postmortem"))

    assert result.documents == ("failover-postmortem",)


async def test_every_search_is_recorded_in_the_run_trace(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """FR-023, and the half of it that makes the ablation readable."""
    await ingestor(gateway, scope, embedder, engine, clock).ingest(
        runbook("payments-failover", FAILOVER)
    )
    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)

    await search.search(KnowledgeQuery(text="replica lag"))
    search.ledger.mark_acted_on("as documented in payments-failover, promote the standby")

    summary = search.ledger.trace_summary()
    assert summary["knowledge_searches"] == 1
    assert summary["knowledge_searches_with_results"] == 1
    assert summary["knowledge_searches_acted_on"] == 1


async def test_a_re_ingested_document_supersedes_rather_than_duplicating(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """A deleted section must not stay retrievable, confident, and wrong."""
    writes = ingestor(gateway, scope, embedder, engine, clock)
    first = await writes.ingest(runbook("payments-failover", FAILOVER))

    shortened = FAILOVER.split("## Failing over")[0]
    second = await writes.ingest(runbook("payments-failover", shortened))

    assert first.document.version == 1
    assert second.document.version == 2
    assert second.superseded is True

    search = KnowledgeSearch(gateway=gateway, scope=scope, embedder=embedder, clock=clock)
    result = await search.search(KnowledgeQuery(text="promote the standby drain the pool"))

    assert all("Promote the standby" not in found.chunk.text for found in result.chunks)


async def test_an_unchanged_document_is_not_re_embedded(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # What makes a nightly sync of a hundred runbooks cost the two that changed.
    writes = ingestor(gateway, scope, embedder, engine, clock)
    await writes.ingest(runbook("payments-failover", FAILOVER))
    again = await writes.ingest(runbook("payments-failover", FAILOVER))

    assert again.outcome.value == "unchanged"
    assert again.document.version == 1


def test_a_requested_limit_is_bounded() -> None:
    assert bounded_limit(0) > 0
    assert bounded_limit(10_000) == MAX_KNOWLEDGE_SEARCH_RESULTS
