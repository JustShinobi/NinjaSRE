"""What the knowledge review queue stores today, pinned before it is generalised.

Three other origins are about to share this queue's propose-screen-store shape,
and the extraction that makes that possible is a refactor of the one path that
already works. Article XII.2 asks for a characterisation test first, so this is
it: not "the queue behaves sensibly" — the suite beside this one already asserts
that — but the exact *stored form*, which is the thing an extraction can change
without any behavioural test noticing.

The stored form matters because it outlives the code. An approval request written
last quarter is read back by whatever this module becomes, so the action string,
the argument keys, the expiry and the rollback plan's single step are a
compatibility surface rather than an implementation detail.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config.constants.knowledge import PROPOSAL_APPROVAL_ACTION, PROPOSAL_REVIEW_TTL_HOURS
from config.constants.security import SIDE_EFFECT_WRITE_REVERSIBLE
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import DocumentType
from platform.knowledge.errors import DocumentRejected
from platform.knowledge.proposals import KnowledgeProposal, ProposalQueue, ProposalState
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
        body="Compare the container memory limit against the previous revision.",
        document_type=DocumentType.RUNBOOK,
        correlation_id="corr-42",
        run_id="run-42",
        rationale="The last three investigations of this alert all ended here.",
        evidence=("run-42/turn-3", "run-40/turn-9"),
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


async def test_the_stored_request_is_the_shape_a_later_reader_expects(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """Action, level, expiry and every argument key, as stored today."""
    await queue(gateway, scope, embedder, engine, clock).propose(proposal())

    async with gateway.begin(scope) as uow:
        request = await uow.approvals.get_request("prop-1")

    assert request is not None
    assert request.action == PROPOSAL_APPROVAL_ACTION
    assert request.side_effect_level == SIDE_EFFECT_WRITE_REVERSIBLE
    assert request.run_id == "run-42"
    assert request.summary == "Payments 5xx after a limit change"
    assert request.requested_at == clock()
    assert request.expires_at == clock() + timedelta(hours=PROPOSAL_REVIEW_TTL_HOURS)
    assert set(request.arguments) == {
        "team_node_id",
        "title",
        "body",
        "document_type",
        "correlation_id",
        "amends",
        "rationale",
        "evidence",
    }
    assert request.arguments["correlation_id"] == "corr-42"
    assert request.arguments["evidence"] == ["run-42/turn-3", "run-40/turn-9"]


async def test_the_rollback_plan_is_stored_in_the_same_breath_as_the_request(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """Article III made structural: the undo exists before anybody can approve."""
    await queue(gateway, scope, embedder, engine, clock).propose(proposal())

    async with gateway.begin(scope) as uow:
        plan = await uow.approvals.rollback_plan_for("prop-1")

    assert plan is not None
    assert plan.plan_id == "prop-1-rollback"
    assert plan.approval_id == "prop-1"
    assert [step.capability for step in plan.steps] == ["knowledge.delete_document"]
    assert plan.steps[0].arguments == {"document_id": "proposed-prop-1"}


async def test_a_proposal_carrying_credential_material_never_reaches_the_store(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """Screened at propose time, so the review queue never holds the secret."""
    carrying = KnowledgeProposal(
        proposal_id="prop-secret",
        org_id=PRIMARY_ORG,
        team_node_id=PAYMENTS_TEAM,
        title="How we reach the metrics API",
        body="Use aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        correlation_id="corr-9",
    )

    with pytest.raises(DocumentRejected):
        await queue(gateway, scope, embedder, engine, clock).propose(carrying)

    async with gateway.begin(scope) as uow:
        assert await uow.approvals.get_request("prop-secret") is None


async def test_approving_records_the_decision_then_writes_the_document(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """The decided row and the document both exist, and the row carries the reviewer."""
    reviews = queue(gateway, scope, embedder, engine, clock)
    await reviews.propose(proposal())

    decision = await reviews.approve("prop-1", reviewer=REVIEWER)

    assert decision.state is ProposalState.APPROVED
    assert decision.document is not None
    async with gateway.begin(scope) as uow:
        request = await uow.approvals.get_request("prop-1")
        stored = await uow.knowledge.get_document("proposed-prop-1")
    assert request is not None
    assert request.decided_by == REVIEWER
    assert stored is not None
