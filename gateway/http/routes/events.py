"""One channel per tenant: what changed in their deployment, not what any of it is.

Everything a run's own stream (`investigations.py`) does for one investigation,
this does for the organisation the caller's token belongs to: watch, reconnect
with `Last-Event-ID`, get a heartbeat while nothing happens. What it does not
do is answer "what is the current state" — a frame here carries an id, never a
title, a summary, or a document, and a client that wants the state re-reads the
route that already serves it (`GET /v1/runs`, `GET /v1/incidents`,
`GET /v1/proposals`, ...).

**Scoped to the caller, not to the process.** This docstring used to argue the
opposite: that the channel named no tenant, so the permission check was the
whole of what it needed and what a viewer may read of any id was settled later,
by the read route they asked for it with. That argument does not survive the
premise being checked. A deployment serves more than one organisation — a token
resolves to whichever organisation its own row names, and a second one is
created by a shipped path — and the broker is one process-wide object that
every tenant's writes publish into. An unscoped feed therefore handed any
holder of the read permission the incident ids, proposal ids, kinds and timings
of every *other* organisation's deployment. That the ids are useless without a
read route is not a defence: their existence, their rate and their timing are
themselves the other tenant's business.

So the caller's own organisation — `auth.scope.org_id`, the authenticated
token's, never a value a request named — is passed down to the broker, and both
the live path and the reconnection backlog are filtered against it there.
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
    """Stream this organisation's runs, incidents and decisions changing, live.

    ``auth`` does two things, not one. It carries the permission check against
    the route table — the same permission `GET /v1/runs` needs — and it names
    the organisation the connection is served, which is the token's own scope
    and nothing a request can influence.
    """
    cursor = parse_deployment_cursor(last_event_id)
    return StreamingResponse(
        deployment_event_source(
            broker=state.deployment_events,
            cursor=cursor,
            org_id=auth.scope.org_id,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
