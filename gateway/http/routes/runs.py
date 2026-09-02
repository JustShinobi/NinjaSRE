"""Runs and traces: list, get, replay.

The same records ``routes/investigations.py`` exposes, from the trace side —
a run outlives the request that started it, and this is where an operator
reviews one after the fact.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from config.constants.investigation import EVIDENCE_ASSESSMENT_CAPABILITY
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.investigations import (
    InvestigationSummary,
    linked_summary,
    stages_of,
    summary_of,
    with_stage,
)
from gateway.http.routes.tenancy import visible
from gateway.http.routes.threads import ThreadCallView, thread_turn_view
from gateway.http.state import GatewayState
from platform.persistence.ports.run_trace_store import RunStatus, ToolCallRecord
from platform.runs.evidence import assessment_from_calls
from platform.runs.replay import ReplayedStage, ReplayedTurn, bounded_result, replay_trace

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class RunList(BaseModel):
    runs: list[InvestigationSummary]


class ReplayCallView(ThreadCallView):
    """One call as a replay serves it: the thread's fields, plus what came back.

    The thread view deliberately stops at "which capability, how it went". A
    replay is read to answer what the run *found*, and a reader that cannot see
    a single result can only list the questions the agent asked — the answers
    are in the trace and were being thrown away here.
    """

    #: What the capability returned, bounded for reading rather than for
    #: storage. See ``platform.runs.replay.bounded_result`` for why the two
    #: bounds differ.
    result: dict[str, Any] = Field(default_factory=dict)
    #: Whether anything was removed from ``result`` — by the recorder on the
    #: way in, or by the bound above on the way out. Either way this is not the
    #: whole body, and a reader is told so rather than left to infer it.
    result_truncated: bool = False


class ReplayTurnView(BaseModel):
    """One turn as a replay serves it, its calls carrying their results.

    The turn's own fields are the thread view's, restated rather than
    inherited: a subclass cannot narrow ``list[ThreadCallView]`` to
    ``list[ReplayCallView]``, because a list is mutable and so invariant. The
    *values* still come from ``thread_turn_view`` below, which is the half that
    could actually drift.
    """

    turn_id: str
    index: int
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: ``None`` when the provider publishes no price for this turn — never a
    #: fabricated ``0.0`` standing in for "unknown".
    cost: float | None = None
    selection_rationale: str = ""
    model_rationale: str = ""
    calls: list[ReplayCallView]


def replay_turn_view(turn: ReplayedTurn) -> ReplayTurnView:
    """Return ``turn`` in the replay's shape.

    Built on top of the thread view rather than beside it: the two differ only
    in what a call carries, and computing the turn's own fields again here is
    how they would come to disagree about a model name or a rationale.
    """
    base = thread_turn_view(turn)
    calls: list[ReplayCallView] = []
    for shared, call in zip(base.calls, turn.calls, strict=True):
        served, truncated = bounded_result(call)
        calls.append(
            ReplayCallView(
                **shared.model_dump(),
                result=served,
                result_truncated=truncated,
            )
        )
    return ReplayTurnView(**base.model_dump(exclude={"calls"}), calls=calls)


class ReplayStageView(BaseModel):
    """One of the six stages, with the turns that ran inside it.

    Five of the six hold no turns and that is the point of serving them. Only
    the gathering stage drives the loop, so a replay of turns alone is a
    detailed account of one stage and silence about the other five — including
    intake and diagnosis, which each spend a model call and turn nothing.
    ``llm_calls`` is what separates "made no turn" from "did nothing", and a
    reader who has only the turn list cannot tell those apart.
    """

    stage: str
    #: The one line the stage wrote about what it established, from the slice
    #: that stage owns. Empty when it established nothing worth a sentence —
    #: never a filler line invented so the section has something in it.
    finding: str = ""
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    failed: bool = False
    turns: list[ReplayTurnView]


def replay_stage_view(stage: ReplayedStage) -> ReplayStageView:
    """Return ``stage`` in the replay's shape, its turns in the turns' shape."""
    return ReplayStageView(
        stage=stage.stage.value,
        finding=stage.finding,
        duration_ms=stage.duration_ms,
        prompt_tokens=stage.prompt_tokens,
        completion_tokens=stage.completion_tokens,
        llm_calls=stage.llm_calls,
        failed=stage.failed,
        turns=[replay_turn_view(turn) for turn in stage.turns],
    )


class RunReplayView(BaseModel):
    run_id: str
    turns: list[ReplayTurnView]
    #: The stages that finished, in the order the pipeline runs them, each
    #: holding the turns that ran inside it. Empty for a run recorded before
    #: stages reached the trace, and for a loop driven without a pipeline —
    #: which is also what tells a reader that ``total_tokens`` below is a floor
    #: rather than a total.
    stages: list[ReplayStageView]
    #: The sum of the turns that carried a recorded cost. Read this with
    #: ``unpriced_turns`` — on its own it is a floor, not a total, and it is a
    #: floor twice over: it counts only priced turns, and the two stages that
    #: call a model without producing a turn are not in it at all. See
    #: ``stages[].llm_calls`` for the calls it cannot price.
    total_cost: float
    #: How many turns carried no recorded cost, because their provider
    #: published none. Never folded into ``total_cost`` as zero.
    unpriced_turns: int
    #: What the whole run spent, every model call included — summed over the
    #: stages when the run recorded any, and over the turns when it did not.
    total_tokens: int
    #: What the loop alone spent. Below ``total_tokens`` on a pipelined run by
    #: exactly the intake and diagnosis calls, which is the gap that made a
    #: run's recorded cost understate its real one.
    turn_tokens: int
    #: How many events the run's own log holds. Served rather than derived from
    #: the turn list, which is what the console was doing: a formula over turns
    #: and calls cannot see the events no turn produced, which is every stage
    #: boundary and every guardrail action.
    total_events: int
    is_interrupted: bool


@router.get("", response_model=RunList)
async def list_runs(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = 50,
    status: Annotated[list[RunStatus] | None, Query()] = None,
    run_id: Annotated[list[str] | None, Query()] = None,
) -> RunList:
    """Return recent runs visible to the caller, newest first.

    Each carries how sure it was, because the list is where somebody decides
    which run to open and "did it actually back this" is the question that
    decides it. Read in one batched query over the whole page rather than one
    per row — the per-row version works on a demo and is a fifty-query page in
    a deployment that has been running a while.

    ``status`` may be repeated, and the page is then the runs in any of them
    — the console's attention band asks for the failed, the cancelled and the
    interrupted runs in one read, where it used to read the whole page and
    keep three rows of it. A word this deployment has no status for is
    refused as a validation error, like any other malformed query.

    ``run_id`` may be repeated too, for a screen that already knows which
    runs it cites — the incidents screen names the run behind each settled
    firing — and would otherwise read a page of fifty to find them.
    """
    async with state.gateway.begin(auth.scope) as uow:
        runs = await uow.run_traces.list_runs(limit=limit, status=status, run_ids=run_id)
        shown = [run for run in runs if visible(run, auth)]
        run_ids = [run.run_id for run in shown]
        assessments = await uow.run_traces.named_tool_calls_for_runs(
            run_ids, EVIDENCE_ASSESSMENT_CAPABILITY
        )
        stages = await stages_of(run_ids, uow)

    by_run: dict[str, list[ToolCallRecord]] = {}
    for call in assessments:
        by_run.setdefault(call.run_id, []).append(call)

    listed: list[InvestigationSummary] = []
    for run in shown:
        assessment = assessment_from_calls(by_run.get(run.run_id, []))
        summary = summary_of(run).model_copy(
            update={
                "evidence_assessed": assessment.assessed,
                "evidence_backed": assessment.backed,
                "evidence_missing": assessment.missing,
            }
        )
        listed.append(with_stage(summary, stages.get(run.run_id, "")))
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
    """Return ``run_id`` reconstructed from its recorded events alone.

    Each call carries what it returned, bounded for reading. The trace has held
    the result since it was recorded; until it was served here, a reader could
    see which capabilities a run asked and not one thing any of them answered,
    which is a transcript of the questions and none of the findings.

    The turns arrive twice, and deliberately: flat in ``turns`` and grouped in
    ``stages``. An investigation is six stages, and only the fourth of them
    runs the loop — so the flat list is a complete account of the gathering and
    says nothing about the classification that decided the run was worth
    starting or the diagnosis that structured what it found. The grouping is
    what a reader wants; the flat list is what a client that has never heard of
    a stage still gets, including for the runs recorded before stages reached
    the trace, whose ``stages`` is empty.
    """
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no run {run_id!r}")
        trace = await uow.run_traces.replay(run_id)
    replayed = replay_trace(trace)
    return RunReplayView(
        run_id=run_id,
        turns=[replay_turn_view(turn) for turn in replayed.turns],
        stages=[replay_stage_view(stage) for stage in replayed.stages],
        total_cost=replayed.total_cost,
        unpriced_turns=replayed.unpriced_turn_count,
        total_tokens=replayed.total_tokens,
        turn_tokens=replayed.turn_tokens,
        total_events=len(replayed.events),
        is_interrupted=replayed.is_interrupted,
    )


__all__ = ["router"]
