"""Agent-proposed knowledge, and the review it cannot get past.

An agent that writes knowledge it later reads, unreviewed, builds a
self-reinforcing belief system with no external correction. The first
investigation's plausible-sounding conclusion becomes a runbook; the second
investigation reads the runbook and concludes the same thing with more
confidence; by the fifth there is a well-cited document describing a cause
nobody ever confirmed. Nothing inside the loop can detect that, which is why the
loop breaker has to be outside it. A human reviewing the proposal is the only
one available.

So the invariant this module exists to hold is a negative, and it is enforced
structurally rather than by care:

**Applying a proposal reads the approval store and refuses on anything but a
recorded approval.** ``propose`` writes to the queue and never to the knowledge
base. ``apply`` is public precisely so a test can attempt the bypass — SC-007 is
asserted by trying it, because a negative nobody tries is a negative nobody has
checked.

Everything else here follows from that. The proposal carries the investigation
that produced it (FR-018), so a reviewer can see the evidence without leaving the
queue. An approved proposal is attributed as agent-originated and human-approved
(FR-019), because a reader who cannot tell an agent's document from an
engineer's has no way to weigh it. And the queue is the approval machinery the
platform already has — a second one would be a second place for the rule to be
almost right.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from config.constants.knowledge import (
    MAX_PROPOSAL_CHARS,
    MAX_PROPOSAL_QUEUE_RESULTS,
    PROPOSAL_APPROVAL_ACTION,
    PROPOSAL_REVIEW_TTL_HOURS,
)
from config.constants.security import SIDE_EFFECT_WRITE_REVERSIBLE
from config.prompts.knowledge import PROPOSAL_ATTRIBUTION
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import IngestionResult, KnowledgeIngestor
from platform.knowledge.base.models import Document, DocumentOrigin, DocumentType
from platform.knowledge.clock import now as _utc_now
from platform.knowledge.errors import DocumentRejected, ProposalNotApproved, ProposalUnknown
from platform.observability.logging import get_logger
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.proposals.models import ProposalState
from platform.proposals.queue import queue_request

logger = get_logger(__name__)

#: How the document id of an approved proposal is built when it is not amending
#: an existing document. Prefixed rather than bare, so a proposal can never
#: collide with a document an operator wrote and silently supersede it.
PROPOSED_DOCUMENT_ID = "proposed-{proposal_id}"

#: The capability an approved proposal's rollback plan calls. Named here because
#: the plan is stored at proposal time, months before anybody might run it.
ROLLBACK_CAPABILITY = "knowledge.delete_document"

#: Keys the proposal keeps inside the approval request's arguments. The request
#: is the stored form: the approval store holds approvals, not knowledge, and
#: teaching it what a runbook is would be the wrong direction of dependency.
BODY_KEY = "body"
TEAM_KEY = "team_node_id"
TITLE_KEY = "title"
TYPE_KEY = "document_type"
CORRELATION_KEY = "correlation_id"
AMENDS_KEY = "amends"
RATIONALE_KEY = "rationale"
EVIDENCE_KEY = "evidence"


@dataclass(frozen=True, slots=True)
class KnowledgeProposal:
    """One knowledge addition or amendment an agent proposed (FR-016)."""

    proposal_id: str
    org_id: str
    team_node_id: str
    title: str
    body: str
    document_type: DocumentType = DocumentType.RUNBOOK
    correlation_id: str = ""
    run_id: str = ""
    amends: str = ""
    rationale: str = ""
    evidence: tuple[str, ...] = ()
    proposed_at: datetime | None = None
    state: ProposalState = ProposalState.PENDING
    decided_by: str = ""
    decided_at: datetime | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("a proposal must have an id")
        if not self.title.strip():
            raise ValueError(f"{self.proposal_id}: a proposal must have a title")
        if not self.body.strip():
            raise ValueError(f"{self.proposal_id}: a proposal must have a body")
        if not self.correlation_id.strip():
            raise ValueError(
                f"{self.proposal_id}: a proposal must name the investigation that produced "
                "it — a reviewer with no evidence to look at is a reviewer who approves it"
            )
        object.__setattr__(self, "body", self.body[:MAX_PROPOSAL_CHARS])

    @property
    def document_id(self) -> str:
        """Return the document this proposal would create or amend."""
        return self.amends.strip() or PROPOSED_DOCUMENT_ID.format(proposal_id=self.proposal_id)

    def arguments(self) -> dict[str, Any]:
        """Return what the approval request stores verbatim.

        The whole proposal, not a reference to it. An approval granted against
        different content than was applied is not an approval, and keeping the
        exact text on the request is what lets an audit prove they matched.
        """
        return {
            TEAM_KEY: self.team_node_id,
            TITLE_KEY: self.title,
            BODY_KEY: self.body,
            TYPE_KEY: self.document_type.value,
            CORRELATION_KEY: self.correlation_id,
            AMENDS_KEY: self.amends,
            RATIONALE_KEY: self.rationale,
            EVIDENCE_KEY: list(self.evidence),
        }

    def to_request(self, *, at: datetime) -> ApprovalRequest:
        """Return the approval request this proposal is stored as."""
        return ApprovalRequest(
            approval_id=self.proposal_id,
            run_id=self.run_id or self.correlation_id,
            action=PROPOSAL_APPROVAL_ACTION,
            # A knowledge write is reversible — the document can be deleted — and
            # the plan that says how is stored beside this request before anybody
            # can approve it.
            side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
            summary=self.title,
            requested_at=at,
            expires_at=at + timedelta(hours=PROPOSAL_REVIEW_TTL_HOURS),
            arguments=self.arguments(),
        )

    @classmethod
    def from_request(cls, request: ApprovalRequest, *, org_id: str) -> KnowledgeProposal:
        """Return the proposal a stored approval request describes."""
        arguments: Mapping[str, Any] = request.arguments
        return cls(
            proposal_id=request.approval_id,
            org_id=org_id,
            team_node_id=str(arguments.get(TEAM_KEY, "")),
            title=str(arguments.get(TITLE_KEY, request.summary)),
            body=str(arguments.get(BODY_KEY, "")),
            document_type=DocumentType.parse(str(arguments.get(TYPE_KEY, ""))),
            correlation_id=str(arguments.get(CORRELATION_KEY, request.run_id)),
            run_id=request.run_id,
            amends=str(arguments.get(AMENDS_KEY, "")),
            rationale=str(arguments.get(RATIONALE_KEY, "")),
            evidence=tuple(str(item) for item in arguments.get(EVIDENCE_KEY) or ()),
            proposed_at=request.requested_at,
            state=ProposalState.of(request.state),
            decided_by=request.decided_by or "",
            decided_at=request.decided_at,
            reason=request.reason or "",
        )

    def as_document(self, *, approved_by: str, approved_at: datetime) -> Document:
        """Return the document this proposal becomes once a human approves it.

        The attribution is a sentence rather than a flag because it is shown to
        whoever later reads the document, and "agent-originated, approved by
        Erik on the 6th" is what they need — not a boolean they would have to
        look up the meaning of.
        """
        return Document(
            document_id=self.document_id,
            org_id=self.org_id,
            team_node_id=self.team_node_id,
            title=self.title,
            body=self.body,
            document_type=self.document_type,
            origin=DocumentOrigin.AGENT_PROPOSED,
            attribution=PROPOSAL_ATTRIBUTION.format(
                correlation_id=self.correlation_id,
                approved_by=approved_by,
                approved_at=approved_at.date().isoformat(),
            ),
            updated_at=approved_at,
        )

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console and the trace read."""
        return {
            "proposal_id": self.proposal_id,
            "team_node_id": self.team_node_id,
            "title": self.title,
            "document_type": self.document_type.value,
            "document_id": self.document_id,
            "correlation_id": self.correlation_id,
            "amends": self.amends,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "state": self.state.value,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
        }


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    """What a review did, and the document it produced when it approved."""

    proposal: KnowledgeProposal
    state: ProposalState
    reason: str = ""
    document: Document | None = None
    ingestion: IngestionResult | None = None

    @property
    def proposal_id(self) -> str:
        """Return the proposal this decision is about."""
        return self.proposal.proposal_id


@dataclass(slots=True)
class ProposalQueue:
    """The review queue: where a proposal waits, and the only way out of it."""

    gateway: PersistenceGateway
    scope: TenantScope
    ingestor: KnowledgeIngestor
    engine: GuardrailEngine | None = None
    clock: Callable[[], datetime] = _utc_now
    _proposed: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: the review queue must be scoped to a team — an "
                "unscoped queue is one that shows another team's proposals"
            )

    async def propose(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        """Queue ``proposal`` for review. Writes nothing to the knowledge base.

        The rollback plan is stored in the same unit of work as the request, not
        later. The approval store refuses to record an approval for a request
        with no plan — Article III's "and" made structural — so storing it here
        is what makes the proposal reviewable at all, and doing it in one
        transaction is what stops a crash leaving a proposal nobody can approve.
        """
        proposal = self._scoped(proposal)
        self._screen(proposal)

        moment = self.clock()
        await queue_request(
            self.gateway,
            self.scope,
            proposal.to_request(at=moment),
            RollbackPlan(
                plan_id=f"{proposal.proposal_id}-rollback",
                approval_id=proposal.proposal_id,
                created_at=moment,
                notes=(
                    "Approving this proposal adds one document to the knowledge base. "
                    "Undoing it deletes that document and its chunks."
                ),
                steps=(
                    RollbackStep(
                        ordinal=1,
                        description=f"Delete the document {proposal.document_id!r}",
                        capability=ROLLBACK_CAPABILITY,
                        arguments={"document_id": proposal.document_id},
                    ),
                ),
            ),
        )

        self._proposed.add(proposal.proposal_id)
        logger.info(
            "knowledge.proposal_queued",
            proposal=proposal.proposal_id,
            correlation_id=proposal.correlation_id,
            amends=proposal.amends,
        )
        return replace(proposal, proposed_at=moment, state=ProposalState.PENDING)

    async def get(self, proposal_id: str) -> KnowledgeProposal | None:
        """Return one proposal, or ``None`` when this team has no such proposal."""
        async with self.gateway.begin(self.scope) as uow:
            request = await uow.approvals.get_request(proposal_id)
        if request is None or request.action != PROPOSAL_APPROVAL_ACTION:
            return None
        proposal = KnowledgeProposal.from_request(request, org_id=self.scope.org_id)
        return proposal if proposal.team_node_id == self.scope.team_node_id else None

    async def pending(
        self, *, limit: int = MAX_PROPOSAL_QUEUE_RESULTS
    ) -> tuple[KnowledgeProposal, ...]:
        """Return this team's undecided proposals, longest-waiting first."""
        async with self.gateway.begin(self.scope) as uow:
            requests = await uow.approvals.list_pending(limit=limit)
        return self._own(requests)

    async def approve(
        self, proposal_id: str, *, reviewer: str, reason: str = ""
    ) -> ProposalDecision:
        """Record an approval and apply the proposal, in that order.

        In that order and not the other, which is the whole point: the decision
        is a row before anything is written, so a crash between the two leaves a
        recorded approval and no document — recoverable by re-applying — rather
        than a document nobody approved.
        """
        decided = await self._decide(
            proposal_id, state=ApprovalState.APPROVED, reviewer=reviewer, reason=reason
        )
        return await self._apply(decided)

    async def reject(self, proposal_id: str, *, reviewer: str, reason: str) -> ProposalDecision:
        """Record a rejection, with the reason kept for whoever proposed it.

        The reason is required. A rejected proposal with no reason teaches
        nothing: the same proposal arrives again after the next investigation of
        the same failure, and the reviewer rejects it again.
        """
        if not reason.strip():
            raise ValueError(
                f"{proposal_id}: a rejection must carry a reason — the same proposal will "
                "arrive again after the next investigation of the same failure"
            )
        decided = await self._decide(
            proposal_id, state=ApprovalState.REJECTED, reviewer=reviewer, reason=reason
        )
        logger.info("knowledge.proposal_rejected", proposal=proposal_id, reviewer=reviewer)
        return ProposalDecision(
            proposal=decided, state=ProposalState.REJECTED, reason=decided.reason
        )

    async def apply(self, proposal_id: str) -> ProposalDecision:
        """Write an **approved** proposal into the knowledge base.

        Public on purpose. This is the method a bypass would call, so it is the
        method SC-007 attempts — and it refuses on anything but an approval that
        is recorded in the store, which is a fact on a row rather than a flag in
        this process.
        """
        proposal = await self.get(proposal_id)
        if proposal is None:
            raise ProposalUnknown(proposal_id)
        if proposal.state is not ProposalState.APPROVED:
            raise ProposalNotApproved(proposal_id, proposal.state.value)
        return await self._apply(proposal)

    async def expire_due(self) -> tuple[KnowledgeProposal, ...]:
        """Expire proposals nobody reviewed in time, and return them.

        A proposal answered a week after the incident is answered by somebody who
        no longer remembers what the cluster looked like, which is not review.
        """
        async with self.gateway.begin(self.scope) as uow:
            expired = await uow.approvals.expire_due(self.clock())
        return self._own(expired)

    # -- internals -------------------------------------------------------------

    def _scoped(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        """Return ``proposal`` bound to this queue's tenant, or raise on a mismatch.

        A proposal arrives from a capability, and a capability has no tenant — it
        is a plain function the model called, and inventing one there is how a
        tool comes to write into the wrong team. So the scope is stamped here,
        from the queue the composition root built. A proposal that *does* name a
        tenant has to name this one: a caller that knows the scope and got it
        wrong is a bug rather than an omission.
        """
        org = proposal.org_id or self.scope.org_id
        team = proposal.team_node_id or (self.scope.team_node_id or "")
        if org != self.scope.org_id or team != self.scope.team_node_id:
            raise ValueError(
                f"{proposal.proposal_id}: this queue serves "
                f"{self.scope.org_id}/{self.scope.team_node_id} and the proposal declares "
                f"{org}/{team}"
            )
        return replace(proposal, org_id=org, team_node_id=team)

    def _screen(self, proposal: KnowledgeProposal) -> None:
        """Raise if the proposal carries credential material.

        Screened at the queue as well as at ingestion. A proposal is written by a
        model that has been reading production output, and a credential in one
        would otherwise sit in the review queue — and in the console showing it —
        until somebody approved or rejected it.
        """
        if self.engine is None:
            return
        scan = self.engine.scan(f"{proposal.title}\n{proposal.body}")
        if scan.clean:
            return
        logger.warning(
            "knowledge.proposal_refused",
            proposal=proposal.proposal_id,
            rules=list(scan.rules_fired),
        )
        raise DocumentRejected(
            proposal.proposal_id,
            (
                f"the guardrail engine detected credential material in the proposed text "
                f"({', '.join(scan.rules_fired)}). The matched text is not reproduced here."
            ),
        )

    async def _decide(
        self,
        proposal_id: str,
        *,
        state: ApprovalState,
        reviewer: str,
        reason: str,
    ) -> KnowledgeProposal:
        """Record one decision and return the proposal as stored afterwards."""
        proposal = await self.get(proposal_id)
        if proposal is None:
            raise ProposalUnknown(proposal_id)

        async with self.gateway.begin(self.scope) as uow:
            decided = await uow.approvals.decide(
                proposal_id,
                state=state,
                decided_by=reviewer,
                decided_at=self.clock(),
                reason=reason or None,
            )
        return KnowledgeProposal.from_request(decided, org_id=self.scope.org_id)

    async def _apply(self, proposal: KnowledgeProposal) -> ProposalDecision:
        """Ingest an approved proposal as a document, attributed."""
        document = proposal.as_document(
            approved_by=proposal.decided_by or "an operator",
            approved_at=proposal.decided_at or self.clock(),
        )
        result = await self.ingestor.ingest(document)
        if result.rejected:
            # Screened twice and refused at the second gate. The approval stands
            # — a human did approve it — but nothing was written, and the reason
            # is what the reviewer is shown.
            logger.warning(
                "knowledge.approved_proposal_rejected_at_ingestion",
                proposal=proposal.proposal_id,
                reason=result.reason,
            )
            return ProposalDecision(
                proposal=proposal,
                state=proposal.state,
                reason=result.reason,
                ingestion=result,
            )

        logger.info(
            "knowledge.proposal_applied",
            proposal=proposal.proposal_id,
            document=document.document_id,
            reviewer=proposal.decided_by,
        )
        return ProposalDecision(
            proposal=proposal,
            state=ProposalState.APPROVED,
            reason=proposal.reason,
            document=result.document,
            ingestion=result,
        )

    def _own(self, requests: Iterable[ApprovalRequest]) -> tuple[KnowledgeProposal, ...]:
        """Return the knowledge proposals among ``requests`` that this team owns."""
        proposals = (
            KnowledgeProposal.from_request(request, org_id=self.scope.org_id)
            for request in requests
            if request.action == PROPOSAL_APPROVAL_ACTION
        )
        return tuple(
            proposal for proposal in proposals if proposal.team_node_id == self.scope.team_node_id
        )


def queued_ids(proposals: Sequence[KnowledgeProposal]) -> tuple[str, ...]:
    """Return the ids of ``proposals``, for a log line or a console listing."""
    return tuple(proposal.proposal_id for proposal in proposals)


__all__ = [
    "PROPOSED_DOCUMENT_ID",
    "ROLLBACK_CAPABILITY",
    "KnowledgeProposal",
    "ProposalDecision",
    "ProposalQueue",
    "ProposalState",
    "queued_ids",
]
