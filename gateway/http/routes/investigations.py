"""Create, read, list, and cancel investigations; the mid-run message queue.

Acceptance scenario 1: a create request returns the run's identity
immediately. ``orchestration.start_investigation`` is what makes that true —
it writes the run row and returns before the investigation itself has taken
a single step.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.constants.runs import TRIGGER_INTERACTIVE
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


class InvestigationList(BaseModel):
    investigations: list[InvestigationSummary]


class QueueMessageRequest(BaseModel):
    text: str = Field(min_length=1)


def _fallback_objective(run: AgentRun) -> str:
    """Return a description of ``run``'s own subject, for a headline synthesised
    from a run this feature never got to write one for.

    Deliberately not richer than this: the alert's name and the resource it
    named live on the request that started the run, not on the stored row,
    and inventing them here would mean guessing. ``alert_id`` and ``trigger``
    are what actually persisted.
    """
    if run.alert_id:
        return f"investigation triggered by {run.alert_id}"
    return f"{run.trigger} investigation" if run.trigger else ""


def summary_of(run: AgentRun) -> InvestigationSummary:
    headline = run.headline or synthesize_headline(objective=_fallback_objective(run))
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


async def linked_summary(run: AgentRun, uow: Any) -> InvestigationSummary:
    """Return ``run``'s summary, plus its incident and the resources it touched.

    The extra two lookups a single-run read pays for and a list never does:
    the incident by a direct, indexed lookup — never a paginated scan — and
    the resources from what this run's own calls were actually made with,
    never from an alert's declared subjects.
    """
    incident = await uow.incidents.find_by_run(run.run_id)
    calls = await uow.run_traces.tool_calls_for_run(run.run_id)
    assessment = assessment_from_calls(calls)
    return summary_of(run).model_copy(
        update={
            "incident_id": incident.incident_id if incident is not None else "",
            "touched_resources": list(touched_resources_of(calls)),
            "evidence_assessed": assessment.assessed,
            "evidence_backed": assessment.backed,
            "evidence_missing": assessment.missing,
        }
    )


@router.post("", response_model=InvestigationSummary, status_code=202)
async def create_investigation(
    body: CreateInvestigationRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> InvestigationSummary:
    """Start an investigation and return its identity immediately."""
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
    return InvestigationSummary(run_id=run_id, trigger=TRIGGER_INTERACTIVE, status="running")


@router.get("", response_model=InvestigationList)
async def list_investigations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    limit: int = 50,
) -> InvestigationList:
    """Return recent investigations visible to the caller, newest first."""
    async with state.gateway.begin(auth.scope) as uow:
        runs = await uow.run_traces.list_runs(limit=limit)
    return InvestigationList(investigations=[summary_of(run) for run in runs if visible(run, auth)])


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
