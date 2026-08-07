"""Grafana's vendor, whose empty answer is a list in some places and a document
in others.

Grafana's API is older than its consistency. Search, annotations, and alert
rules answer JSON arrays; the datasource query endpoint answers a keyed
``results`` document; the rest answer objects. A client reading a list where the
vendor sent an object raises, which would surface as "Grafana is broken" in a
scenario that meant "there were no dashboards matching".
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

#: Endpoints whose empty answer is an array rather than a document.
_LIST_ENDPOINTS: Final[tuple[str, ...]] = (
    "/api/search",
    "/api/annotations",
    "/api/datasources",
    "/api/alertmanager",
    "/api/v1/rules",
    "/api/v1/provisioning/alert-rules",
)

_QUERY_ENDPOINT: Final = "/api/ds/query"


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a Grafana instance with nothing to report answers."""
    if _QUERY_ENDPOINT in request.path:
        return json_response({"results": {}})
    if any(request.path.startswith(prefix) for prefix in _LIST_ENDPOINTS):
        return json_response([])
    return json_response({})


BACKENDS: Final[tuple[MockBackend, ...]] = (
    MockBackend(
        integration="grafana",
        empty=empty,
        recorded_from="curl -H 'Authorization: Bearer ...' against a test Grafana's HTTP API",
    ),
)


__all__ = ["BACKENDS", "empty"]
