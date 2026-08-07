"""Pending interactions, visible and answerable through the API (acceptance scenario 9).

Approving and rejecting are both answers — ``selected_option`` carries which —
so ``InvestigationRunner`` needs one closing method rather than three, and this
module is the place that vocabulary is spelled out for a client.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.agent.interaction.models import Interaction, Question
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.routes.tenancy import visible
from gateway.http.state import GatewayState

investigations_router = APIRouter(prefix="/v1/investigations/{run_id}", tags=["interactions"])
interactions_router = APIRouter(prefix="/v1/interactions", tags=["interactions"])

APPROVE_OPTION = "approve"
REJECT_OPTION = "reject"


class InteractionView(BaseModel):
    interaction_id: str
    run_id: str
    kind: str
    text: str
    reason: str = ""
    options: list[str] = Field(default_factory=list)
    is_open: bool


class InteractionList(BaseModel):
    interactions: list[InteractionView]


class AnswerRequest(BaseModel):
    text: str = Field(min_length=1)
    selected_option: str = ""


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


def _view(interaction: Interaction) -> InteractionView:
    return InteractionView(
        interaction_id=interaction.interaction_id,
        run_id=interaction.run_id,
        kind=interaction.kind.value,
        text=interaction.describe(),
        reason=interaction.reason if isinstance(interaction, Question) else "",
        options=list(interaction.options) if isinstance(interaction, Question) else [],
        is_open=interaction.is_open,
    )


@investigations_router.get("/interactions", response_model=InteractionList)
async def list_interactions(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InteractionList:
    """Return one investigation's open questions and approvals."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")
    pending = await state.investigator.pending_interactions(run_id)
    return InteractionList(interactions=[_view(interaction) for interaction in pending])


async def _authorised_interaction(
    interaction_id: str, state: GatewayState, auth: AuthenticatedRequest
) -> Interaction:
    """Return the interaction, or 404 if it does not exist or belongs to another team."""
    found = await state.investigator.find_interaction(interaction_id)
    if found is None:
        raise not_found(f"no interaction {interaction_id!r}")
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(found.run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no interaction {interaction_id!r}")
    return found


@interactions_router.post("/{interaction_id}/answer", response_model=InteractionView)
async def answer(
    interaction_id: str,
    body: AnswerRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InteractionView:
    """Answer a pending question."""
    await _authorised_interaction(interaction_id, state, auth)
    closed = await state.investigator.answer_interaction(
        interaction_id,
        text=body.text,
        principal=auth.principal_id,
        selected_option=body.selected_option,
    )
    return _view(closed)


@interactions_router.post("/{interaction_id}/approve", response_model=InteractionView)
async def approve(
    interaction_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InteractionView:
    """Approve a pending change, closing it."""
    found = await _authorised_interaction(interaction_id, state, auth)
    if found.kind.value != "approval":
        raise bad_request(f"{interaction_id!r} is a {found.kind.value}, not an approval")
    closed = await state.investigator.answer_interaction(
        interaction_id, text="approved", principal=auth.principal_id, selected_option=APPROVE_OPTION
    )
    return _view(closed)


@interactions_router.post("/{interaction_id}/reject", response_model=InteractionView)
async def reject(
    interaction_id: str,
    body: RejectRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InteractionView:
    """Reject a pending change, with a reason, closing it."""
    found = await _authorised_interaction(interaction_id, state, auth)
    if found.kind.value != "approval":
        raise bad_request(f"{interaction_id!r} is a {found.kind.value}, not an approval")
    closed = await state.investigator.answer_interaction(
        interaction_id, text=body.reason, principal=auth.principal_id, selected_option=REJECT_OPTION
    )
    return _view(closed)


__all__ = ["interactions_router", "investigations_router"]
