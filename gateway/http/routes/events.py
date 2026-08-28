"""One channel, deployment-scoped: what changed anywhere, not what any of it is.

Everything a run's own stream (`investigations.py`) does for one investigation,
this does for the deployment: watch, reconnect with `Last-Event-ID`, get a
heartbeat while nothing happens. What it does not do is answer "what is the
current state" — a frame here carries an id, never a title, a summary, or a
document, and a client that wants the state re-reads the route that already
serves it (`GET /v1/runs`, `GET /v1/incidents`, `GET /v1/proposals`, ...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from gateway.http.streaming.subscription import deployment_event_source, parse_deployment_cursor

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.get("/stream")
async def stream_deployment_events(
    request: Request,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream the deployment's runs, incidents and decisions changing, live.

    ``auth`` is required and checked against the route table (the same
    permission `GET /v1/runs` needs) but otherwise unused: this channel is not
    scoped to a tenant, a run, or anything else the caller names — it is one
    process-wide feed, and what each viewer may read of any given id is still
    decided, as always, by the read route they ask for it with.
    """
    # `authorized` already ran the permission check as a side effect of being
    # resolved; nothing in the body reads who the caller is, because this
    # channel names no tenant, run or id of its own for a caller's identity to
    # be checked against — see the docstring.
    del auth
    cursor = parse_deployment_cursor(last_event_id)
    return StreamingResponse(
        deployment_event_source(
            broker=state.deployment_events,
            cursor=cursor,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
