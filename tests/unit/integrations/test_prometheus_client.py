"""The one Prometheus endpoint ``query_range`` adds beside the two already there.

``query_instant`` and ``query_metric`` already reach Prometheus; this proves
``query_range`` asks the same range endpoint ``query_metric`` does, but as one
unpaginated call with an explicit step — the shape ``PrometheusMetricsSource``
needs for the bridge's ``history()`` and nothing else.
"""

from __future__ import annotations

import json

import pytest

from integrations._base.transport import RequestContext
from integrations.prometheus.client import QUERY_METRIC_PATH, PrometheusClient
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

CONTEXT = RequestContext(org_id="acme", team_id="-", capability="observation.tick")


class _Transport:
    def __init__(self, body: object) -> None:
        self.body = body
        self.sent: list[ProxyRequest] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.sent.append(request)
        return OutboundResponse(status_code=200, body=json.dumps(self.body).encode("utf-8"))


async def test_query_range_asks_the_range_endpoint_with_an_explicit_step() -> None:
    transport = _Transport(
        {"status": "success", "data": {"result": [{"metric": {}, "values": []}]}}
    )
    client = PrometheusClient(transport=transport, context=CONTEXT)

    await client.query_range("node_bridge_up", start="1000", end="2000", step="30s")

    assert len(transport.sent) == 1
    url = transport.sent[0].url
    assert QUERY_METRIC_PATH in url
    assert "query=node_bridge_up" in url
    assert "start=1000" in url
    assert "end=2000" in url
    assert "step=30s" in url


async def test_query_range_returns_every_result_row_unpaginated() -> None:
    rows = [{"metric": {"bridge": "vmbr0"}, "values": [[1000, "1"], [1030, "0"]]}]
    transport = _Transport({"status": "success", "data": {"result": rows}})
    client = PrometheusClient(transport=transport, context=CONTEXT)

    result = await client.query_range("node_bridge_up", start="1000", end="2000", step="30s")

    assert result == tuple(rows)
