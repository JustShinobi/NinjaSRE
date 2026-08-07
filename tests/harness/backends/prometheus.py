"""Prometheus' vendor, and the envelope that means "the query matched nothing".

Prometheus never answers "no data" with an error or an empty body. It answers
``status: success`` with an empty ``result``, and the difference matters: a
client that got an error would surface a broken metrics backend, while one that
gets this correctly reports that the series is flat. A scenario where the agent
looked at CPU and found nothing is a scenario about an agent that looked.

The result type follows the endpoint, because a range query and an instant
query return different shapes and a client that unpacked the wrong one would
report an empty range as a malformed answer.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

_RANGE_ENDPOINT: Final = "query_range"
_LABEL_ENDPOINTS: Final[tuple[str, ...]] = ("/label", "/series", "/targets", "/rules")


def envelope(result_type: str) -> dict[str, object]:
    """Return an empty Prometheus response envelope of ``result_type``."""
    return {"status": "success", "data": {"resultType": result_type, "result": []}}


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a Prometheus server with nothing to report answers."""
    if any(marker in request.path for marker in _LABEL_ENDPOINTS):
        return json_response({"status": "success", "data": []})
    if _RANGE_ENDPOINT in request.url:
        return json_response(envelope("matrix"))
    return json_response(envelope("vector"))


BACKENDS: Final[tuple[MockBackend, ...]] = tuple(
    MockBackend(
        integration=name,
        empty=empty,
        recorded_from="curl against /api/v1/query and /api/v1/query_range on a test server",
    )
    # VictoriaMetrics and Thanos-shaped vendors answer the same envelope, which
    # is the whole reason the Prometheus API became the interface it is.
    for name in ("prometheus", "victoriametrics")
)


__all__ = ["BACKENDS", "empty", "envelope"]
