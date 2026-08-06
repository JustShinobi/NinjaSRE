"""No proposal reaches the knowledge base without a human, asserted by attempting it.

SC-007 is a negative, and a negative is only worth asserting if the test tries
the thing. So this suite does: it queues a proposal, checks the corpus is
untouched, calls the application step directly while the review is pending, and
requires a refusal. Then it rejects a second proposal and tries again.

The invariant is not "the queue is careful". It is that applying a proposal reads
the approval store and refuses on anything but a recorded approval — so the only
way to get a document in is for somebody to have decided, and the decision is on
a row rather than in a variable.
"""

from __future__ import annotations

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import DocumentOrigin, DocumentType
from platform.knowledge.proposals import (
    KnowledgeProposal,
    ProposalNotApproved,
    ProposalQueue,
    ProposalState,
)
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import PAYMENTS_TEAM, PRIMARY_ORG, Clock

pytestmark = pytest.mark.unit

REVIEWER = "erik@example.com"


def proposal(proposal_id: str = "prop-1") -> KnowledgeProposal:
    """Return one agent-authored proposal, carrying its investigation."""
    return KnowledgeProposal(
        proposal_id=proposal_id,
        org_id=PRIMARY_ORG,
        team_node_id=PAYMENTS_TEAM,
        title="Payments 5xx after a limit change",
        body=(
            "# Payments 5xx after a limit change\n\n"
            "When payments returns 5xx shortly after a deploy, compare the container "
            "memory limit against the previous revision before looking at the database.\n"
        ),
        document_type=DocumentType.RUNBOOK,
        correlation_id="corr-42",
        run_id="run-42",
        rationale="The last three investigations of this alert all ended here.",
    )


def queue(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> ProposalQueue:
    """Return a review queue over a real ingestor."""
    return ProposalQueue(
        gateway=gateway,
        scope=scope,
        ingestor=KnowledgeIngestor(
            gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
        ),
        engine=engine,
        clock=clock,
    )


async def test_a_proposal_writes_nothing_to_the_knowledge_base(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """SC-007, first half: proposing is not writing."""
    reviews = queue(gateway, scope, embedder, engine, clock)

    queued = await reviews.propose(proposal())

    assert queued.state is ProposalState.PENDING
    async with gateway.begin(scope) as uow:
        assert await uow.knowledge.list_documents() == ()
        assert await uow.knowledge.count_chunks() == 0


async def test_applying_a_pending_proposal_is_refused(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """SC-007, second half: the bypass, attempted."""
    reviews = queue(gateway, scope, embedder, engine, clock)
    await reviews.propose(proposal())

    with pytest.raises(ProposalNotApproved):
        await reviews.apply("prop-1")

    async with gateway.begin(scope) as uow:
        assert await uow.knowledge.count_chunks() == 0


async def test_applying_a_rejected_proposal_is_refused(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    reviews = queue(gateway, scope, embedder, engine, clock)
    await reviews.propose(proposal())

    decision = await reviews.reject("prop-1", reviewer=REVIEWER, reason="already documented")
    assert decision.state is ProposalState.REJECTED
    assert decision.reason == "already documented"

    with pytest.raises(ProposalNotApproved):
        await reviews.apply("prop-1")

    async with gateway.begin(scope) as uow:
        assert await uow.knowledge.count_chunks() == 0


async def test_an_approved_proposal_lands_attributed(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """FR-019: agent-originated, human-approved, and it says so on the document."""
    reviews = queue(gateway, scope, embedder, engine, clock)
    await reviews.propose(proposal())

    decision = await reviews.approve("prop-1", reviewer=REVIEWER)

    assert decision.state is ProposalState.APPROVED
    assert decision.document is not None
    assert decision.document.origin is DocumentOrigin.AGENT_PROPOSED
    assert "corr-42" in decision.document.attribution
    assert REVIEWER in decision.document.attribution

    async with gateway.begin(scope) as uow:
        stored = await uow.knowledge.get_document(decision.document.document_id)
        assert stored is not None
        assert await uow.knowledge.count_chunks() > 0


async def test_a_proposal_records_the_investigation_that_produced_it(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """FR-018: a reviewer can see the evidence without leaving the queue."""
    reviews = queue(gateway, scope, embedder, engine, clock)
    await reviews.propose(proposal())

    pending = await reviews.pending()

    assert [item.proposal_id for item in pending] == ["prop-1"]
    assert pending[0].correlation_id == "corr-42"
    assert pending[0].rationale.startswith("The last three investigations")
