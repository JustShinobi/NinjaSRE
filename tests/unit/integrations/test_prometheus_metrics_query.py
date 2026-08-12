"""The sentence between the vendor's paging vocabulary and a signal source."""

from __future__ import annotations

import pytest

from integrations.prometheus.metrics_query import PrometheusMetrics

pytestmark = pytest.mark.unit


class _Pages:
    def __init__(self, items: tuple[object, ...], truncated: bool = False) -> None:
        self.items = items
        self.truncated = truncated
        self.pages_followed = 1


class _Client:
    def __init__(self, pages: _Pages) -> None:
        self.pages = pages
        self.asked: list[str] = []

    async def query_metric(self, expression: str = "") -> _Pages:
        self.asked.append(expression)
        return self.pages


async def test_the_expression_reaches_the_client_and_the_series_come_back() -> None:
    client = _Client(_Pages(({"metric": {"id": "lxc/100"}, "value": [1, "0.5"]},)))

    series = await PrometheusMetrics(client=client).evaluate("pve_up")  # type: ignore[arg-type]

    assert client.asked == ["pve_up"]
    assert series == ({"metric": {"id": "lxc/100"}, "value": [1, "0.5"]},)


async def test_a_truncated_walk_is_said_out_loud(caplog: pytest.LogCaptureFixture) -> None:
    """A guest missing from a result reads exactly like a guest with nothing
    to say, so a stopped walk must not arrive silently."""
    client = _Client(_Pages((), truncated=True))

    with caplog.at_level("WARNING"):
        await PrometheusMetrics(client=client).evaluate("pve_up")  # type: ignore[arg-type]

    assert "truncated" in caplog.text


def test_the_client_can_be_pointed_at_the_operators_own_endpoint() -> None:
    """The shipped region is a placeholder — nobody packaging this knows where
    your Prometheus is. A client that could only be permitted to reach the
    operator's host, never pointed at it, asks example.com for ever.
    """
    from integrations._base.transport import RequestContext
    from integrations.prometheus.client import PrometheusClient

    context = RequestContext(org_id="acme", team_id="-", capability="observation.tick")

    class _Transport:
        async def forward(self, request: object) -> object:
            raise AssertionError("not called")

    shipped = PrometheusClient(transport=_Transport(), context=context)  # type: ignore[arg-type]
    pointed = PrometheusClient(
        transport=_Transport(),  # type: ignore[arg-type]
        context=context,
        base_url="http://10.20.20.37:9090",
    )

    assert "example.com" in shipped.base_url
    assert pointed.base_url.startswith("http://10.20.20.37:9090")


async def test_a_pressure_reading_asks_for_an_instant_not_a_range() -> None:
    """A range query without a window is a 400, and a pressure signal is one
    number now rather than a series: /api/v1/query, not /api/v1/query_range."""
    from integrations.prometheus.client import INSTANT_QUERY_PATH

    asked: list[tuple[str, object]] = []

    class _Client:
        async def query_instant(self, expression: str) -> tuple[object, ...]:
            asked.append((INSTANT_QUERY_PATH, expression))
            return ()

    await PrometheusMetrics(client=_Client()).evaluate("pve_up")  # type: ignore[arg-type]

    assert asked == [("/api/v1/query", "pve_up")]
