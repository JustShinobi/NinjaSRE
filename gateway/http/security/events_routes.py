"""The deployment-wide event channel's one route, and what it takes to reach it.

Watching the channel is a read of the same facts `GET /v1/runs` already
answers — a run started, a run finished — plus the incident and decision
equivalents this deployment already exposes their own read routes for.
Reusing `INVESTIGATION_READ` rather than declaring a new permission is the
same call `gateway_routes.py` already made for the per-run stream: seeing the
change live is not a distinct capability from seeing it at all.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

EVENTS_ROUTES: Final[tuple[Route, ...]] = (
    Route(method="GET", path="/v1/events/stream", permission=Permission.INVESTIGATION_READ),
)

__all__ = ["EVENTS_ROUTES"]
