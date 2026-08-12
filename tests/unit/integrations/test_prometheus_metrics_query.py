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
