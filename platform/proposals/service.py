"""The queue: where a proposal waits, and the only way out of it.

One object per team, holding the four things every origin needs to agree on:

**Nothing is applied without a decision on a row.** ``apply`` is public on
purpose — it is the method a bypass would call, so it is the method the negative
test attempts — and it reads the store rather than a flag in this process.
Approving is two steps in one order: record the decision, then carry it out. A
crash between them leaves an approval and no change, which is recoverable; the
other order leaves a change nobody approved, which is not.

**The undo is written before the decision exists.** The applier is asked how it
would reverse the change at ``propose`` time, and the plan is stored in the same
unit of work as the request. Article III's requirement is an "and", and this is
where the "and" becomes impossible to skip.

**A rejection is data.** It carries a reason, the reason is stored, and a later
proposal with the same correlation key can read every earlier refusal of the
same thing. The screen shows the pattern; nothing here decides on it. A queue
that auto-rejected the fourth attempt would be a queue that had taken the
decision away from the person the whole design exists to keep.

**The queue serves one team — or the whole organisation.** The store is scoped
to an organisation; the narrowing to a node is here, because a review queue
showing another team's proposals is one where the wrong person approves a
change to somebody else's cluster. A scope that names no team is the
organisation's own — an operator whose credential is org-wide is every team's
reviewer, not none of them — and the boundary that matters remains ``org_id``,
which the scope always carries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from config.constants.proposals import (
    MAX_DECIDED_PROPOSAL_HISTORY,
    MAX_RECALLED_REJECTIONS,
)
from platform.guardrails.engine import GuardrailEngine
from platform.observability.logging import get_logger
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.proposals.errors import ProposalRefused
from platform.proposals.models import (
    AgentProposal,
    PriorRejection,
    ProposalState,
    ProposalType,
)
from platform.proposals.queue import proposals_among, queue_request
from platform.proposals.screening import SecretFields, screen

logger = get_logger(__name__)


class ProposalUnknown(Exception):
    """No proposal with that identifier belongs to this team."""

    def __init__(self, proposal_id: str) -> None:
        super().__init__(f"{proposal_id}: this team has no such proposal")


class ProposalNotApproved(Exception):
    """Somebody tried to apply a proposal nobody approved."""

    def __init__(self, proposal_id: str, state: str) -> None:
        self.state = state
        super().__init__(
            f"{proposal_id} is {state}, and only an approved proposal is applied. "
            f"A change nobody decided on is a change nobody is answerable for."
        )


@runtime_checkable
class ProposalApplier(Protocol):
    """Whatever knows how to carry one kind of proposal out, and to undo it.

    Two methods, and the first is why this is a protocol rather than a callback:
    the reversal has to be written down *before* the decision, so the thing that
    knows how to apply a change is asked how to reverse it at the moment the
    change is proposed rather than at the moment somebody approves it.
    """

    async def rollback_steps(self, proposal: AgentProposal) -> Sequence[RollbackStep]:
        """Return the steps that would undo ``proposal``, ordered as executed."""

    async def apply(self, proposal: AgentProposal, *, approved_by: str) -> str:
        """Carry ``proposal`` out and return one line saying what happened."""


@dataclass(frozen=True, slots=True)
class ProposalOutcome:
    """What a review did, and what the applier reported when it approved."""

    proposal: AgentProposal
    state: ProposalState
    reason: str = ""
    applied: str = ""

    @property
    def proposal_id(self) -> str:
        """Return the proposal this outcome is about."""
        return self.proposal.proposal_id


@dataclass(frozen=True, slots=True)
class Acceptance:
    """How this team has answered proposals, as a figure the queue shows.

    Both numbers, never the ratio alone. "60%" over five decisions and "60%"
    over two hundred are different facts, and a screen showing only the
    percentage would let the first pass for the second.
    """

    decided: int = 0
    approved: int = 0

    @property
    def rate(self) -> float:
        """Return the accepted share, or ``0.0`` when nothing has been decided."""
        return self.approved / self.decided if self.decided else 0.0

    def to_record(self) -> dict[str, float | int]:
        """Return the JSON-serialisable form the queue screen reads."""
        return {"decided": self.decided, "approved": self.approved, "rate": self.rate}


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(slots=True)
class ProposalQueue:
    """Every proposal this scope has been asked to decide, and the deciding.

    A scope naming a team is that team's queue and sees nobody else's rows. A
    scope naming only the organisation is the organisation's queue and sees
    every team's — the shape an org-wide operator credential arrives in.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    #: One per origin this deployment can actually carry out. A type with no
    #: applier cannot be proposed, which is the correct failure: a deployment
    #: with no detectors should refuse a detector proposal at the queue rather
    #: than accept one it could never honour.
    appliers: Mapping[ProposalType, ProposalApplier]
    credentials: SecretFields | None = None
    guardrails: GuardrailEngine | None = None
    clock: Callable[[], datetime] = _utc_now

    @property
    def actions(self) -> frozenset[str]:
        """Return the approval actions this queue's proposals are stored under."""
        return frozenset(kind.action for kind in self.appliers)

    async def propose(self, proposal: AgentProposal) -> AgentProposal:
        """Queue ``proposal`` for review. Applies nothing.

        Refuses before it stores, so a proposal that names a credential or the
        containment never reaches a screen; and stores the rollback plan in the
        same unit of work as the request, so a crash cannot leave a proposal
        nobody can ever approve.
        """
        proposal = self._scoped(proposal)
        applier = self.appliers.get(proposal.proposal_type)
        if applier is None:
            raise ProposalRefused(
                proposal.proposal_id,
                f"is a {proposal.proposal_type.value} proposal, and this deployment has "
                f"nothing that applies one. Nothing is queued that could never be carried out.",
            )
        screen(proposal, credentials=self.credentials, guardrails=self.guardrails)

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
                    f"Undoing this restores {proposal.target!r} to what it was before the "
                    f"proposal was applied."
                ),
                steps=tuple(await applier.rollback_steps(proposal)),
            ),
        )

        logger.info(
            "proposal.queued",
            proposal=proposal.proposal_id,
            kind=proposal.proposal_type.value,
            run=proposal.run_id,
        )
        return replace(proposal, proposed_at=moment, state=ProposalState.PENDING)

    async def get(self, proposal_id: str) -> AgentProposal | None:
        """Return one proposal, or ``None`` when this team has no such proposal."""
        async with self.gateway.begin(self.scope) as uow:
            request = await uow.approvals.get_request(proposal_id)
        return self._own(request)

    async def pending(
        self, *, limit: int = MAX_DECIDED_PROPOSAL_HISTORY
    ) -> tuple[AgentProposal, ...]:
        """Return this team's undecided proposals, longest-waiting first."""
        async with self.gateway.begin(self.scope) as uow:
            requests = await uow.approvals.list_pending(limit=limit)
        return self._mine(requests)

    async def decided(
        self, *, limit: int = MAX_DECIDED_PROPOSAL_HISTORY
    ) -> tuple[AgentProposal, ...]:
        """Return this team's answered proposals, most recently decided first."""
        found: list[AgentProposal] = []
        async with self.gateway.begin(self.scope) as uow:
            for action in sorted(self.actions):
                found.extend(
                    self._mine(await uow.approvals.list_decided(action=action, limit=limit))
                )
        found.sort(key=lambda item: item.decided_at or item.proposed_at or _EPOCH, reverse=True)
        return tuple(found[:limit])

    async def prior_rejections(
        self, correlation_id: str, *, limit: int = MAX_RECALLED_REJECTIONS
    ) -> tuple[PriorRejection, ...]:
        """Return what was said the last few times this same thing was refused.

        Matched on the correlation key rather than on the text: two runs
        proposing the same detector word it differently, and a recall that
        compared summaries would show nothing in exactly the case it exists for.
        """
        if not correlation_id.strip():
            return ()
        return tuple(
            PriorRejection(
                proposal_id=item.proposal_id,
                reason=item.reason,
                decided_by=item.decided_by,
                decided_at=item.decided_at,
            )
            for item in await self.decided()
            if item.state is ProposalState.REJECTED and item.correlation_id == correlation_id
        )[:limit]

    async def acceptance(self) -> Acceptance:
        """Return how many proposals this team has answered, and how many it took."""
        history = await self.decided()
        return Acceptance(
            decided=len(history),
            approved=sum(1 for item in history if item.state is ProposalState.APPROVED),
        )

    async def approve(
        self, proposal_id: str, *, reviewer: str, reason: str = ""
    ) -> ProposalOutcome:
        """Record an approval and apply the proposal, in that order."""
        decided = await self._decide(
            proposal_id, state=ApprovalState.APPROVED, reviewer=reviewer, reason=reason
        )
        return await self._apply(decided)

    async def reject(self, proposal_id: str, *, reviewer: str, reason: str) -> ProposalOutcome:
        """Record a rejection, with the reason kept for whoever proposes it next.

        The reason is required. A rejection with no reason teaches nothing: the
        same proposal arrives after the next investigation of the same failure,
        and the reviewer refuses it again for a reason nobody wrote down either.
        """
        if not reason.strip():
            raise ValueError(
                f"{proposal_id}: a rejection must carry a reason — the same proposal will "
                "arrive again after the next investigation of the same failure"
            )
        decided = await self._decide(
            proposal_id, state=ApprovalState.REJECTED, reviewer=reviewer, reason=reason
        )
        logger.info("proposal.rejected", proposal=proposal_id, reviewer=reviewer)
        return ProposalOutcome(
            proposal=decided, state=ProposalState.REJECTED, reason=decided.reason
        )

    async def apply(self, proposal_id: str) -> ProposalOutcome:
        """Carry out an **approved** proposal.

        Public on purpose. This is the method a bypass would call, so it is the
        method the negative test attempts — and it refuses on anything but an
        approval recorded in the store, which is a fact on a row rather than a
        flag in this process.
        """
        proposal = await self.get(proposal_id)
        if proposal is None:
            raise ProposalUnknown(proposal_id)
        if proposal.state is not ProposalState.APPROVED:
            raise ProposalNotApproved(proposal_id, proposal.state.value)
        return await self._apply(proposal)

    # -- internals -------------------------------------------------------------

    def _scoped(self, proposal: AgentProposal) -> AgentProposal:
        """Return ``proposal`` bound to this queue's tenant, or raise on a mismatch.

        An organisation-scoped queue keeps whatever team the proposal declares:
        it serves them all, and inventing one here would move a proposal into a
        team nobody chose.
        """
        org = proposal.org_id or self.scope.org_id
        own_team = self.scope.team_node_id or ""
        team = proposal.team_node_id or own_team
        if org != self.scope.org_id or (own_team and team != own_team):
            raise ValueError(
                f"{proposal.proposal_id}: this queue serves "
                f"{self.scope.org_id}/{self.scope.team_node_id} and the proposal declares "
                f"{org}/{team}"
            )
        return replace(proposal, org_id=org, team_node_id=team, node_id=proposal.node_id or team)

    def _own(self, request: ApprovalRequest | None) -> AgentProposal | None:
        """Return the proposal ``request`` holds, if it is one and it is ours."""
        if request is None or request.action not in self.actions:
            return None
        proposal = AgentProposal.from_request(request, org_id=self.scope.org_id)
        if proposal is None:
            return None
        if self.scope.team_node_id and proposal.team_node_id != self.scope.team_node_id:
            return None
        return proposal

    def _mine(self, requests: Sequence[ApprovalRequest]) -> tuple[AgentProposal, ...]:
        """Return this team's proposals among ``requests``, order preserved."""
        found = (self._own(request) for request in proposals_among(requests, actions=self.actions))
        return tuple(item for item in found if item is not None)

    async def _decide(
        self, proposal_id: str, *, state: ApprovalState, reviewer: str, reason: str
    ) -> AgentProposal:
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
        answered = AgentProposal.from_request(decided, org_id=self.scope.org_id)
        if answered is None:  # pragma: no cover — the action was checked by ``get``
            raise ProposalUnknown(proposal_id)
        return answered

    async def _apply(self, proposal: AgentProposal) -> ProposalOutcome:
        """Hand an approved proposal to the applier for its type."""
        applier = self.appliers[proposal.proposal_type]
        applied = await applier.apply(proposal, approved_by=proposal.decided_by or "an operator")
        logger.info(
            "proposal.applied",
            proposal=proposal.proposal_id,
            kind=proposal.proposal_type.value,
            reviewer=proposal.decided_by,
        )
        return ProposalOutcome(
            proposal=proposal,
            state=ProposalState.APPROVED,
            reason=proposal.reason,
            applied=applied,
        )


#: The instant an undated proposal sorts as. Only reachable for a record whose
#: store lost both timestamps, and a fixed value keeps the sort total rather
#: than raising in a listing.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


__all__ = [
    "Acceptance",
    "ProposalApplier",
    "ProposalNotApproved",
    "ProposalOutcome",
    "ProposalQueue",
    "ProposalUnknown",
]
