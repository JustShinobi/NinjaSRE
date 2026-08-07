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
    summary: str | None = None


class InvestigationList(BaseModel):
    investigations: list[InvestigationSummary]


class QueueMessageRequest(BaseModel):
    text: str = Field(min_length=1)


def summary_of(run: AgentRun) -> InvestigationSummary:
    return InvestigationSummary(
        run_id=run.run_id,
        trigger=run.trigger,
        status=run.status.value,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        summary=run.summary,
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
    return summary_of(run)


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
