"""Contract: knowledge documents and the chunks retrieval returns."""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import (
    KnowledgeChunk,
    KnowledgeDocument,
    PersistenceGateway,
    TenantScope,
)

pytestmark = pytest.mark.contract

RUNBOOK = KnowledgeDocument(
    document_id="doc-1",
    title="Checkout runbook",
    checksum="sha256:v1",
    source_uri="https://wiki.example.com/checkout",
    updated_at=at(),
)


def chunk(chunk_id: str, *, ordinal: int, text: str = "Restart the pool.") -> KnowledgeChunk:
    """Return a chunk of the runbook."""
    return KnowledgeChunk(chunk_id=chunk_id, document_id="doc-1", ordinal=ordinal, text=text)


async def test_a_document_round_trips_and_is_found_by_its_source(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Checksum lookup by URI is what keeps a nightly sync of a hundred runbooks
    # paying only for the ones that changed.
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(RUNBOOK)

        assert await uow.knowledge.get_document("doc-1") == RUNBOOK
        found = await uow.knowledge.find_document_by_uri("https://wiki.example.com/checkout")

    assert found is not None
    assert found.checksum == "sha256:v1"


async def test_chunks_come_back_in_ordinal_order(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A passage quoted without its neighbours is how a conditional instruction
    # becomes an unconditional one.
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(RUNBOOK)
        await uow.knowledge.replace_chunks(
            "doc-1", [chunk("c-2", ordinal=1), chunk("c-1", ordinal=0)]
        )
        chunks = await uow.knowledge.chunks_for_document("doc-1")

    assert [item.chunk_id for item in chunks] == ["c-1", "c-2"]


async def test_replacing_chunks_leaves_nothing_of_the_old_set(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A deleted section must not stay retrievable, confident, and wrong."""
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(RUNBOOK)
        await uow.knowledge.replace_chunks(
            "doc-1",
            [chunk("c-1", ordinal=0), chunk("c-2", ordinal=1, text="Page the DBA.")],
        )
        await uow.knowledge.replace_chunks("doc-1", [chunk("c-1", ordinal=0)])

        assert await uow.knowledge.get_chunk("c-2") is None
        assert await uow.knowledge.count_chunks() == 1


async def test_chunks_for_a_document_that_does_not_exist_are_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.knowledge.replace_chunks("no-such-doc", [chunk("c-1", ordinal=0)])


async def test_deleting_a_document_takes_its_chunks(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The opposite of the config hierarchy's refusal to cascade, and for the
    # opposite reason: a chunk without its document has no provenance and
    # cannot be shown to anybody.
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(RUNBOOK)
        await uow.knowledge.replace_chunks("doc-1", [chunk("c-1", ordinal=0)])

        assert await uow.knowledge.delete_document("doc-1") is True
        assert await uow.knowledge.count_chunks() == 0
        assert await uow.knowledge.delete_document("doc-1") is False


async def test_documents_are_listed_most_recently_updated_first(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(RUNBOOK)
        await uow.knowledge.upsert_document(
            KnowledgeDocument(
                document_id="doc-2",
                title="Database failover",
                checksum="sha256:v1",
                updated_at=at(60),
            )
        )
        listed = await uow.knowledge.list_documents()

    assert [document.document_id for document in listed] == ["doc-2", "doc-1"]
