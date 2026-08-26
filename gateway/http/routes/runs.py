"""Runs and traces: list, get, replay.

The same records ``routes/investigations.py`` exposes, from the trace side —
a run outlives the request that started it, and this is where an operator
reviews one after the fact.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config.constants.investigation import EVIDENCE_ASSESSMENT_CAPABILITY
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.investigations import InvestigationSummary, linked_summary, summary_of
from gateway.http.routes.tenancy import visible
from gateway.http.routes.threads import ThreadTurnView, thread_turn_view
from gateway.http.state import GatewayState
from platform.persistence.ports.run_trace_store import ToolCallRecord
from platform.runs.evidence import assessment_from_calls
from platform.runs.replay import replay_trace

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class RunList(BaseModel):
    runs: list[InvestigationSummary]


class RunReplayView(BaseModel):
    run_id: str
    turns: list[ThreadTurnView]
    #: The sum of the turns that carried a recorded cost. Read this with
    #: ``unpriced_turns`` — on its own it is a floor, not a total.
    total_cost: float
    #: How many turns carried no recorded cost, because their provider
    #: published none. Never folded into ``total_cost`` as zero.
    unpriced_turns: int
    total_tokens: int
    is_interrupted: bool


@router.get("", response_model=RunList)
async def list_runs(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = 50,
) -> RunList:
    """Return recent runs visible to the caller, newest first.

    Each carries how sure it was, because the list is where somebody decides
    which run to open and "did it actually back this" is the question that
    decides it. Read in one batched query over the whole page rather than one
    per row — the per-row version works on a demo and is a fifty-query page in
    a deployment that has been running a while.
    """
    async with state.gateway.begin(auth.scope) as uow:
        runs = await uow.run_traces.list_runs(limit=limit)
        shown = [run for run in runs if visible(run, auth)]
        assessments = await uow.run_traces.named_tool_calls_for_runs(
            [run.run_id for run in shown], EVIDENCE_ASSESSMENT_CAPABILITY
        )

    by_run: dict[str, list[ToolCallRecord]] = {}
    for call in assessments:
        by_run.setdefault(call.run_id, []).append(call)

    listed: list[InvestigationSummary] = []
    for run in shown:
        assessment = assessment_from_calls(by_run.get(run.run_id, []))
        listed.append(
            summary_of(run).model_copy(
                update={
                    "evidence_assessed": assessment.assessed,
                    "evidence_backed": assessment.backed,
                    "evidence_missing": assessment.missing,
                }
            )
        )
    return RunList(runs=listed)


@router.get("/{run_id}", response_model=InvestigationSummary)
async def get_run(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Return one run."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no run {run_id!r}")
        return await linked_summary(run, uow)


@router.get("/{run_id}/replay", response_model=RunReplayView)
async def replay(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RunReplayView:
    """Return ``run_id`` reconstructed from its recorded events alone."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no run {run_id!r}")
        trace = await uow.run_traces.replay(run_id)
    replayed = replay_trace(trace)
    return RunReplayView(
        run_id=run_id,
        turns=[thread_turn_view(turn) for turn in replayed.turns],
        total_cost=replayed.total_cost,
        unpriced_turns=replayed.unpriced_turn_count,
        total_tokens=replayed.total_tokens,
        is_interrupted=replayed.is_interrupted,
    )


__all__ = ["router"]
