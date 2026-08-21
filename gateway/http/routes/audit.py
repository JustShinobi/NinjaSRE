"""The record: browsable with filters, exportable as a stream.

Two routes and one query. Browsing and exporting differ in how much comes back
and in nothing else, which is deliberate: an export that ran a different query
from the screen it was launched from would be an export nobody could reconcile
against what they were looking at.

The export is newline-delimited JSON rather than a single array, so a consumer
can process it as it arrives and a tenant's whole history never has to be held
in one buffer at either end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request
from gateway.http.state import GatewayState
from platform.persistence.ports.audit_repository import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])

EXPORT_MEDIA_TYPE = "application/x-ndjson"


class AuditEventView(BaseModel):
    event_id: str
    occurred_at: str
    actor_kind: str
    actor_id: str
    action: str
    resource_kind: str
    resource_id: str
    outcome: str
    detail: dict[str, Any]


class AuditEventList(BaseModel):
    events: list[AuditEventView]
    total: int


def _view(event: AuditEvent) -> AuditEventView:
    return AuditEventView(
        event_id=event.event_id,
        occurred_at=event.occurred_at.isoformat(),
        actor_kind=event.actor_kind.value,
        actor_id=event.actor_id,
        action=event.action,
        resource_kind=event.resource_kind,
        resource_id=event.resource_id,
        outcome=event.outcome.value,
        detail=dict(event.detail),
    )


def _instant(value: str, field_name: str) -> datetime | None:
    """Return ``value`` as an instant, or ``None`` when it is empty."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as malformed:
        raise bad_request(f"{field_name} is not an ISO 8601 instant") from malformed


@router.get("/events", response_model=AuditEventList)
async def list_events(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    actor_id: str = "",
    action: str = "",
    resource_kind: str = "",
    resource_id: str = "",
    since: str = "",
    until: str = "",
    limit: int = 100,
) -> AuditEventList:
    """Return matching audit events, most recent first (FR-025)."""
    window_start = _instant(since, "since")
    window_end = _instant(until, "until")
    async with state.gateway.begin(auth.scope) as uow:
        events = await uow.audit.query(
            actor_id=actor_id or None,
            action=action or None,
            resource_kind=resource_kind or None,
            resource_id=resource_id or None,
            since=window_start,
            until=window_end,
            limit=limit,
        )
        total = await uow.audit.count(since=window_start, until=window_end)
    return AuditEventList(events=[_view(event) for event in events], total=total)


@router.get("/export")
async def export_events(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    actor_id: str = "",
    action: str = "",
    resource_kind: str = "",
    resource_id: str = "",
    since: str = "",
    until: str = "",
) -> StreamingResponse:
    """Stream the same records a listing would show, as newline-delimited JSON.

    Paged internally on the event's own instant rather than an offset: an
    append-only log grows underneath a paging offset, and an offset-paged export
    of one would skip records.
    """
    window_start = _instant(since, "since")
    window_end = _instant(until, "until")

    async def records() -> AsyncIterator[bytes]:
        cursor = window_end
        seen: set[str] = set()
        while True:
            async with state.gateway.begin(auth.scope) as uow:
                page = await uow.audit.query(
                    actor_id=actor_id or None,
                    action=action or None,
                    resource_kind=resource_kind or None,
                    resource_id=resource_id or None,
                    since=window_start,
                    until=cursor,
                    limit=MAX_QUERY_PAGE_SIZE,
                )
            fresh = [event for event in page if event.event_id not in seen]
            if not fresh:
                return
            for event in fresh:
                seen.add(event.event_id)
                yield _view(event).model_dump_json().encode() + b"\n"
            if len(page) < MAX_QUERY_PAGE_SIZE:
                return
            cursor = fresh[-1].occurred_at

    return StreamingResponse(
        records(),
        media_type=EXPORT_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="audit.ndjson"'},
    )


__all__ = ["router"]
