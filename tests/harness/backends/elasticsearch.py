"""The search vendors, whose empty answer is a hit envelope with no hits.

Elasticsearch and its relatives never answer a search with an empty body. They
answer a complete envelope reporting zero hits, and a client that unpacks
``hits.hits`` finds a list rather than a missing key. Handing one ``{}`` instead
would raise inside the client, which is the failure this whole fallback exists
to avoid.

``aggregations`` is present and empty for the same reason: a query that asked
for a terms aggregation and got no key back is a client crash, not a quiet
window.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

_SEARCH_ENDPOINTS: Final[tuple[str, ...]] = ("_search", "_async_search", "_count")


def hit_envelope() -> dict[str, object]:
    """Return a complete search response reporting no hits."""
    return {
        "took": 0,
        "timed_out": False,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {"total": {"value": 0, "relation": "eq"}, "max_score": None, "hits": []},
        "aggregations": {},
    }


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a search cluster with nothing to report answers."""
    if any(marker in request.path for marker in _SEARCH_ENDPOINTS):
        return json_response(hit_envelope())
    return json_response({})


BACKENDS: Final[tuple[MockBackend, ...]] = tuple(
    MockBackend(
        integration=name,
        empty=empty,
        recorded_from="the response body of a real _search, with document sources scrubbed",
    )
    for name in ("elasticsearch", "opensearch")
)


__all__ = ["BACKENDS", "empty", "hit_envelope"]
