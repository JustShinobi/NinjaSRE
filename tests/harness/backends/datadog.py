"""Datadog's vendor, whose three API generations answer three empty shapes.

The v2 endpoints answer ``{"data": [], "meta": {}}``; the v1 metric endpoints
answer ``{"series": [], "status": "ok"}``; the v1 monitor and event endpoints
answer a bare array. Which one a client gets depends on the path it called, so
that is what this keys on rather than on the integration name.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

_V2_PREFIX: Final = "/api/v2/"
_METRIC_ENDPOINTS: Final[tuple[str, ...]] = ("/api/v1/query", "/api/v1/series")
_LIST_ENDPOINTS: Final[tuple[str, ...]] = ("/api/v1/monitor", "/api/v1/downtime")


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a Datadog account with nothing to report answers."""
    path = request.path
    if path.startswith(_V2_PREFIX):
        return json_response({"data": [], "meta": {"page": {}}})
    if any(path.startswith(prefix) for prefix in _METRIC_ENDPOINTS):
        return json_response({"status": "ok", "series": [], "from_date": 0, "to_date": 0})
    if any(path.startswith(prefix) for prefix in _LIST_ENDPOINTS):
        return json_response([])
    if path.startswith("/api/v1/events"):
        return json_response({"events": [], "status": "ok"})
    return json_response({})


BACKENDS: Final[tuple[MockBackend, ...]] = (
    MockBackend(
        integration="datadog",
        empty=empty,
        recorded_from="the response body of a real /api/v2/logs/events/search, with hosts and "
        "service names replaced by the scenario's own",
    ),
)


__all__ = ["BACKENDS", "empty"]
