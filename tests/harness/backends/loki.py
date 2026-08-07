"""Loki's vendor: the Prometheus envelope, with streams where the vectors are.

Loki answers log queries in the shape Prometheus answers metric queries, which
means an empty result is ``status: success`` and an empty ``result`` list — not
an error, and not an absent body. A log store that answered an error for "no
lines matched" would turn every quiet window into an incident about the log
store.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

_LABEL_ENDPOINTS: Final[tuple[str, ...]] = ("/labels", "/label", "/series")


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a Loki instance with nothing to report answers."""
    if any(marker in request.path for marker in _LABEL_ENDPOINTS):
        return json_response({"status": "success", "data": []})
    return json_response(
        {"status": "success", "data": {"resultType": "streams", "result": [], "stats": {}}}
    )


BACKENDS: Final[tuple[MockBackend, ...]] = tuple(
    MockBackend(
        integration=name,
        empty=empty,
        recorded_from="curl against /loki/api/v1/query_range on a test instance",
    )
    for name in ("loki", "victorialogs")
)


__all__ = ["BACKENDS", "empty"]
