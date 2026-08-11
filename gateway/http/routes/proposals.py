"""The queue of everything the agent has proposed, and the deciding of it.

Read-heavy on purpose. A proposal is decided in one place — ``POST
/{proposal_id}/decision`` — and everything else here exists so the person
deciding has what they need before they do: the evidence, the run it came out
of, where to see the effect, and what was said the last few times this same
thing was refused.

**The count is one endpoint, read twice.** The sidebar badge and the dashboard's
attention band ask the same question and must not be able to disagree about the
answer, so neither counts rows for itself.

**Nothing here renders an effect.** The effect of a configuration proposal is
``POST /v1/config/{node_id}/preview`` and of a detector proposal is ``POST
/v1/detectors/{id}/dry-run``; both already exist and both are the mechanism the
change would actually go through. A second renderer in this router would be a
second answer to "what would this do", and the day it drifted somebody would
approve one thing having read another.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.proposals import MAX_DECIDED_PROPOSAL_HISTORY
from gateway.http.catalogue_readers import installed_catalogue, installed_integrations
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.state import GatewayState
from platform.approvals.appliers import proposal_appliers_for
from platform.config_service.service import ConfigService
from platform.proposals.models import AgentProposal
from platform.proposals.service import ProposalQueue

router = APIRouter(prefix="/v1/proposals", tags=["proposals"])


class EffectView(BaseModel):
    mechanism: str
    target: str


class PriorRejectionView(BaseModel):
    proposal_id: str
    reason: str
    decided_by: str
    decided_at: str | None = None


class ProposalView(BaseModel):
    proposal_id: str
    proposal_type: str
    node_id: str
    summary: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    #: The investigation this came out of. Empty is impossible for anything the
    #: validator let through, and the field is still typed as a string rather
    #: than required so a row written before this feature reads rather than 500s.
    run_id: str = ""
    correlation_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    effect: EffectView
    state: str
    proposed_at: str | None = None
    decided_at: str | None = None
    decided_by: str = ""
    reason: str = ""
    #: What was said the last few times this same thing was refused. Present on
    #: the single-proposal read and absent from the listing, because it costs a
    #: history scan per row and a queue is read far more often than a proposal.
    prior_rejections: list[PriorRejectionView] = Field(default_factory=list)


class AcceptanceView(BaseModel):
    decided: int
    approved: int
    rate: float


class ProposalList(BaseModel):
    proposals: list[ProposalView]
    acceptance: AcceptanceView


class ProposalCount(BaseModel):
    """What the sidebar badge and the dashboard band both read."""

    pending: int


class DecisionRequest(BaseModel):
    verdict: str
    #: Required to reject, ignored on an approval. A rejection with no reason
    #: teaches nothing: the same proposal arrives after the next investigation
    #: of the same failure and is refused again for a reason nobody wrote down.
    reason: str = ""


class DecisionResult(BaseModel):
    proposal_id: str
    state: str
    applied: str = ""


def _queue(state: GatewayState, auth: AuthenticatedRequest) -> ProposalQueue:
    """Return the review queue for the caller's team, over the live registries."""
    scope = auth.scope
    if not scope.team_node_id:
        raise bad_request(
            "a review queue is a team's. Use a token scoped to the team whose proposals "
            "you are answering."
        )
    config = ConfigService(
        gateway=state.gateway,
        scope=scope,
        guardrails=state.guardrails,
        catalogue=installed_catalogue(),
        integrations=installed_integrations(),
    )
    return ProposalQueue(
        gateway=state.gateway,
        scope=scope,
        appliers=proposal_appliers_for(config=config),
        credentials=InstalledSecretFields(),
        guardrails=state.guardrails,
    )


class InstalledSecretFields:
    """What the installed integrations call secret, for the proposal screen.

    The same question the configuration validator answers, asked of the same
    directory. Not the validator itself only because the queue is built below
    the service that holds one — and the directory is the source both read, so
    the two cannot disagree about what a secret field is called.
    """

    __slots__ = ()

    def secret_field_names(self) -> frozenset[str]:
        """Return every field name an installed integration's schema calls secret."""
        directory = installed_integrations()
        found: set[str] = set()
        for name in directory.names():
            schema = directory.schema(name)
            if schema is None:
                continue
            found.update(declared.name for declared in schema.credential_fields if declared.secret)
            found.update(declared.name for declared in schema.settings_fields if declared.secret)
        return frozenset(found)


def _view(proposal: AgentProposal, *, prior: tuple[Any, ...] = ()) -> ProposalView:
    record = proposal.to_record()
    return ProposalView(
        proposal_id=proposal.proposal_id,
        proposal_type=proposal.proposal_type.value,
        node_id=proposal.node_id,
        summary=proposal.summary,
        rationale=proposal.rationale,
        evidence=list(proposal.evidence),
        run_id=proposal.run_id,
        correlation_id=proposal.correlation_id,
        payload=dict(proposal.payload),
        effect=EffectView(**proposal.effect.to_record()),
        state=proposal.state.value,
        proposed_at=record["proposed_at"],
        decided_at=record["decided_at"],
        decided_by=proposal.decided_by,
        reason=proposal.reason,
        prior_rejections=[
            PriorRejectionView(
                proposal_id=item.proposal_id,
                reason=item.reason,
                decided_by=item.decided_by,
                decided_at=item.decided_at.isoformat() if item.decided_at else None,
            )
            for item in prior
        ],
    )


@router.get("", response_model=ProposalList)
async def list_proposals(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = MAX_DECIDED_PROPOSAL_HISTORY,
) -> ProposalList:
    """Return what is waiting on this team, longest-waiting first.

    The acceptance figure travels with the list rather than on an endpoint of
    its own. It is a property of the queue — how this team has answered — and a
    second request for one number is a second thing to be out of date.
    """
    queue = _queue(state, auth)
    pending = await queue.pending(limit=limit)
    acceptance = await queue.acceptance()
    return ProposalList(
        proposals=[_view(proposal) for proposal in pending],
        acceptance=AcceptanceView(**acceptance.to_record()),  # type: ignore[arg-type]
    )


@router.get("/count", response_model=ProposalCount)
async def count_proposals(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProposalCount:
    """Return how many proposals are waiting, for the badge and the band."""
    return ProposalCount(pending=len(await _queue(state, auth).pending()))


@router.get("/{proposal_id}", response_model=ProposalView)
async def get_proposal(
    proposal_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProposalView:
    """Return one proposal with everything a decision rests on."""
    queue = _queue(state, auth)
    proposal = await queue.get(proposal_id)
    if proposal is None:
        raise not_found(f"no proposal {proposal_id!r}")
    return _view(proposal, prior=await queue.prior_rejections(proposal.correlation_id))


@router.post("/{proposal_id}/decision", response_model=DecisionResult)
async def decide_proposal(
    proposal_id: str,
    request: DecisionRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DecisionResult:
    """Approve or reject a proposal, in the caller's name.

    A rejection without a reason is refused here as well as in the console. A
    control is a courtesy and a server check is a rule, and the reason is what
    the next proposal of the same thing is read against.
    """
    queue = _queue(state, auth)
    if await queue.get(proposal_id) is None:
        raise not_found(f"no proposal {proposal_id!r}")

    reviewer = auth.principal_id
    if request.verdict == "approve":
        outcome = await queue.approve(proposal_id, reviewer=reviewer, reason=request.reason)
    elif request.verdict == "reject":
        if not request.reason.strip():
            raise bad_request(
                "a rejection carries a reason. The same proposal arrives again after the "
                "next investigation of the same failure, and the reason is what stops it."
            )
        outcome = await queue.reject(proposal_id, reviewer=reviewer, reason=request.reason)
    else:
        raise bad_request(f"{request.verdict!r} is not a verdict; use 'approve' or 'reject'")

    return DecisionResult(
        proposal_id=outcome.proposal_id,
        state=outcome.state.value,
        applied=outcome.applied,
    )


__all__ = ["InstalledSecretFields", "router"]
