"""Create, read, list, and cancel investigations; the mid-run message queue.

Acceptance scenario 1: a create request returns the run's identity
immediately. ``orchestration.start_investigation`` is what makes that true —
it writes the run row and returns before the investigation itself has taken
a single step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.constants.runs import TRIGGER_INTERACTIVE
from core.state.types import StageName
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.orchestration import start_investigation
from gateway.http.routes.tenancy import visible
from gateway.http.state import GatewayState
from gateway.http.streaming.subscription import event_source, parse_cursor
from platform.persistence.ports.run_trace_store import AgentRun
from platform.runs.evidence import assessment_from_calls
from platform.runs.headline import synthesize_headline
from platform.runs.replay import touched_resources_of

router = APIRouter(prefix="/v1/investigations", tags=["investigations"])


class CreateInvestigationRequest(BaseModel):
    objective: str = Field(min_length=1)
    alert_source: str = ""
    context: dict[str, str] = Field(default_factory=dict)


class InvestigationSummary(BaseModel):
    run_id: str
    trigger: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    #: One sentence naming the run — stored, or synthesised from the run's
    #: own record when none was ever stored. Never empty for a run that
    #: exists.
    headline: str = ""
    #: The document the model wrote, in full, unaltered. What ``summary``
    #: held alone before this feature.
    report: str = ""
    #: Superseded by ``headline`` and ``report`` above, which this field now
    #: duplicates by serving the same text as ``report`` — kept only until
    #: the console reads the two new fields instead.
    summary: str | None = None
    #: The incident this run belongs to, or the empty string when it
    #: belongs to none — populated on a single-run read only (``GET
    #: /v1/investigations/{run_id}`` and ``GET /v1/runs/{run_id}``), never on
    #: a list, and distinguishable from a failed read by the response having
    #: succeeded at all.
    incident_id: str = ""
    #: Resources this run's own calls touched, derived from what was
    #: recorded — never from the alert's declared subjects. Populated on the
    #: same single-run reads as ``incident_id``.
    touched_resources: list[str] = Field(default_factory=list)
    #: Whether this run completed an assessment of its own evidence. False is
    #: "it never said", never "it said nothing was backed" — a surface that
    #: read the two counts without this would give a silent run the same
    #: chip as a run that found nothing missing.
    evidence_assessed: bool = False
    #: How many pieces of evidence the run named as supporting its conclusion,
    #: and how many it named as still missing. Counted from the run's own
    #: ``assess_evidence_sufficiency`` call rather than scored here.
    evidence_backed: int = 0
    evidence_missing: int = 0
    #: What the run named, in its own words. Populated on a single-run read
    #: only, for the same reason ``touched_resources`` is: a list needs the
    #: counts above, and only a reader who opened one run wants the sentences.
    evidence_supporting_names: list[str] = Field(default_factory=list)
    evidence_missing_names: list[str] = Field(default_factory=list)
    #: The name of the last of the six stages this run completed, or the
    #: empty string for one that has not finished any yet. Never inferred
    #: from ``status`` — a run that is still ``running`` and one that
    #: finished ``failed`` both read this the same way, from the trace.
    last_completed_stage: str = ""
    #: ``last_completed_stage``'s 1-based position among the six, for a
    #: progress bar to size itself by — 0 when none has completed.
    stage_index: int = 0


class InvestigationList(BaseModel):
    investigations: list[InvestigationSummary]


class QueueMessageRequest(BaseModel):
    text: str = Field(min_length=1)


#: The six stages' 1-based position, in the order the pipeline runs them —
#: the same order ``StageName`` declares. Derived here rather than stored:
#: gravar o índice duplicaria uma ordem que o enum já é a única fonte de.
_STAGE_INDEX: Mapping[str, int] = {
    stage.value: position for position, stage in enumerate(StageName, start=1)
}


def stage_index_of(stage: str) -> int:
    """Return ``stage``'s 1-based position among the six, or 0 for none."""
    return _STAGE_INDEX.get(stage, 0)


def summary_of(run: AgentRun) -> InvestigationSummary:
    """Return ``run`` in the shape every read route serves it.

    ``headline`` is either what the run itself carries — the objective it
    started with, an alert's own sentence, or the delivery's, depending on
    how far the run has gotten — or, for a run recorded before either
    column existed, a headline synthesised from nothing: this never falls
    back to ``alert_id``, which is an identifier and never a subject.
    """
    headline = run.headline or synthesize_headline(objective=run.objective)
    return InvestigationSummary(
        run_id=run.run_id,
        trigger=run.trigger,
        status=run.status.value,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        headline=headline,
        report=run.summary or "",
        summary=run.summary,
    )


async def stages_of(run_ids: Sequence[str], uow: Any) -> Mapping[str, str]:
    """Return each of ``run_ids``' last completed stage, in one query.

    A thin pass-through kept here so every reader of this module's
    ``InvestigationSummary`` fetches stages the same way — a list that
    called the store directly would be a second place this batching rule
    could be forgotten.
    """
    return await uow.run_traces.last_completed_stages(run_ids)


def with_stage(summary: InvestigationSummary, stage: str) -> InvestigationSummary:
    """Return ``summary`` carrying ``stage`` and the index it derives."""
    return summary.model_copy(
        update={"last_completed_stage": stage, "stage_index": stage_index_of(stage)}
    )


async def linked_summary(run: AgentRun, uow: Any) -> InvestigationSummary:
    """Return ``run``'s summary, plus its incident and the resources it touched.

    The extra lookups a single-run read pays for and a list never does: the
    incident by a direct, indexed lookup — never a paginated scan — the
    resources from what this run's own calls were actually made with, never
    from an alert's declared subjects, and this run's own last completed
    stage, from the same store method a list uses for a whole page.
    """
    incident = await uow.incidents.find_by_run(run.run_id)
    calls = await uow.run_traces.tool_calls_for_run(run.run_id)
    assessment = assessment_from_calls(calls)
    stages = await stages_of((run.run_id,), uow)
    summary = summary_of(run).model_copy(
        update={
            "incident_id": incident.incident_id if incident is not None else "",
            "touched_resources": list(touched_resources_of(calls)),
            "evidence_assessed": assessment.assessed,
            "evidence_backed": assessment.backed,
            "evidence_missing": assessment.missing,
            "evidence_supporting_names": list(assessment.supporting),
            "evidence_missing_names": list(assessment.missing_evidence),
        }
    )
    return with_stage(summary, stages.get(run.run_id, ""))


@router.post("", response_model=InvestigationSummary, status_code=202)
async def create_investigation(
    body: CreateInvestigationRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Start an investigation and return its identity, headline already named.

    ``start_investigation`` has already committed the row — with its
    provisional headline — by the time it returns the identity, so reading it
    back here costs one query and never a guess at what the row says.
    """
    if state.draining:
        raise bad_request(
            "this deployment is shutting down and is not accepting new investigations"
        )
    run_id = await start_investigation(
        state,
        scope=auth.scope,
        trigger=TRIGGER_INTERACTIVE,
        objective=body.objective,
        principal_id=auth.principal_id,
        alert_source=body.alert_source,
        context=body.context,
    )
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None:  # pragma: no cover — start_investigation just committed this row
        raise RuntimeError(f"start_investigation returned {run_id!r} but the row is not there")
    return summary_of(run)


@router.get("", response_model=InvestigationList)
async def list_investigations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = 50,
) -> InvestigationList:
    """Return recent investigations visible to the caller, newest first."""
    async with state.gateway.begin(auth.scope) as uow:
        runs = await uow.run_traces.list_runs(limit=limit)
        shown = [run for run in runs if visible(run, auth)]
        stages = await stages_of([run.run_id for run in shown], uow)
    return InvestigationList(
        investigations=[
            with_stage(summary_of(run), stages.get(run.run_id, "")) for run in shown
        ]
    )


@router.get("/{run_id}", response_model=InvestigationSummary)
async def get_investigation(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Return one investigation, or 404 if it does not exist or is another team's."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no investigation {run_id!r}")
        return await linked_summary(run, uow)


@router.post("/{run_id}/cancel", response_model=InvestigationSummary)
async def cancel_investigation(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Ask a running investigation to stop at its next safe point."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")
    await state.investigator.cancel(run_id)
    return summary_of(run)


@router.post("/{run_id}/take-over", response_model=InvestigationSummary)
async def take_over_investigation(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Suspend a run at its next safe point so a person can drive it.

    Not a cancellation. A taken-over run keeps its evidence and can be handed
    back; the difference is the whole reason an operator reaches for one rather
    than the other, and a surface that offered only ``cancel`` would make
    "let me look at this myself" cost the investigation.
    """
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")
    await state.investigator.take_over(run_id, principal=auth.principal_id)
    return summary_of(run)


@router.post("/{run_id}/resume", response_model=InvestigationSummary)
async def resume_investigation(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Hand a taken-over run back to the agent, with what the person did in context."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")
    await state.investigator.resume(run_id)
    return summary_of(run)


@router.get("/{run_id}/stream")
async def stream_investigation(
    run_id: str,
    request: Request,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream a run's events live; reconnect with ``Last-Event-ID`` to catch up (FR-009, FR-010)."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")

    cursor = parse_cursor(run_id, last_event_id)
    return StreamingResponse(
        event_source(
            gateway=state.gateway,
            scope=auth.scope,
            is_disconnected=request.is_disconnected,
            broker=state.broker,
            run_id=run_id,
            cursor=cursor,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/messages", status_code=202)
async def queue_message(
    run_id: str,
    body: QueueMessageRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> dict[str, Any]:
    """Queue a message for delivery on the run's next turn."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    if run is None or not visible(run, auth):
        raise not_found(f"no investigation {run_id!r}")
    await state.investigator.queue_message(run_id, body.text)
    return {"run_id": run_id, "queued": True}


__all__ = ["router"]
