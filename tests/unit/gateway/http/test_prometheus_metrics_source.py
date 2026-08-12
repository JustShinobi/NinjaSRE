"""Prometheus as the bridge's ``MetricsSource``: what ``series``/``history`` need.

Nothing here talks to real Prometheus. ``PrometheusClient`` already carries the
paths and the paging; this is the translation from its raw JSON rows to the
bridge's own ``MetricSeries``/``MetricPoint``, and the one place a Prometheus
outage becomes ``MetricsSourceUnreachable`` rather than a bare exception a
detector's tick would not know how to classify.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway.http.prometheus_metrics_source import PrometheusMetricsSource
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from platform.observation.bridge.errors import MetricsSourceUnreachable

pytestmark = pytest.mark.unit


class _Client:
    integration = "prometheus"

    def __init__(
        self,
        *,
        instant: dict[str, tuple[dict[str, object], ...]] | None = None,
        ranged: dict[str, tuple[dict[str, object], ...]] | None = None,
        fails: bool = False,
    ) -> None:
        self._instant = instant or {}
        self._ranged = ranged or {}
        self._fails = fails
        self.instant_calls: list[str] = []
        self.range_calls: list[tuple[str, str, str, str]] = []

    async def query_instant(self, expression: str) -> tuple[dict[str, object], ...]:
        self.instant_calls.append(expression)
        if self._fails:
            raise IntegrationError(
                "prometheus did not answer",
                integration="prometheus",
                reason=IntegrationErrorReason.UPSTREAM_ERROR,
            )
        return self._instant.get(expression, ())

    async def query_range(
        self, expression: str, *, start: str, end: str, step: str
    ) -> tuple[dict[str, object], ...]:
        self.range_calls.append((expression, start, end, step))
        if self._fails:
            raise IntegrationError(
                "prometheus did not answer",
                integration="prometheus",
                reason=IntegrationErrorReason.UPSTREAM_ERROR,
            )
        return self._ranged.get(expression, ())


AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


async def test_series_translates_an_instant_row_into_one_point() -> None:
    client = _Client(
        instant={
            "node_bridge_up": (
                {
                    "metric": {
                        "__name__": "node_bridge_up",
                        "instance": "pve01:9100",
                        "bridge": "vmbr0",
                    },
                    "value": [1755000000, "0"],
                },
            )
        }
    )
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    series = await source.series(matchers=("node_bridge_up",), at=AT)

    assert len(series) == 1
    assert series[0].metric == "node_bridge_up"
    assert series[0].labels == {"instance": "pve01:9100", "bridge": "vmbr0"}
    assert series[0].samples == (series[0].newest,)
    assert series[0].newest is not None
    assert series[0].newest.value == 0.0


async def test_series_issues_one_call_per_matcher_and_combines_them() -> None:
    client = _Client(
        instant={
            "a": ({"metric": {"__name__": "a"}, "value": [1755000000, "1"]},),
            "b": ({"metric": {"__name__": "b"}, "value": [1755000000, "2"]},),
        }
    )
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    series = await source.series(matchers=("a", "b"), at=AT)

    assert client.instant_calls == ["a", "b"]
    assert {entry.metric for entry in series} == {"a", "b"}


async def test_series_raises_metrics_source_unreachable_on_a_client_failure() -> None:
    client = _Client(fails=True)
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    with pytest.raises(MetricsSourceUnreachable):
        await source.series(matchers=("node_bridge_up",), at=AT)


async def test_history_translates_every_value_in_the_window_into_a_point() -> None:
    client = _Client(
        ranged={
            "node_bridge_up": (
                {
                    "metric": {"__name__": "node_bridge_up", "bridge": "vmbr0"},
                    "values": [[1755000000, "1"], [1755000030, "0"]],
                },
            )
        }
    )
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    series = await source.history(
        matchers=("node_bridge_up",),
        start=datetime(2026, 8, 12, 11, 0, tzinfo=UTC),
        end=AT,
        step_seconds=30,
    )

    assert len(series) == 1
    assert len(series[0].samples) == 2
    assert [point.value for point in series[0].samples] == [1.0, 0.0]


async def test_history_passes_the_window_and_step_to_the_client() -> None:
    start = datetime(2026, 8, 12, 11, 0, tzinfo=UTC)
    client = _Client()
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    await source.history(matchers=("node_bridge_up",), start=start, end=AT, step_seconds=30)

    assert client.range_calls == [
        ("node_bridge_up", str(int(start.timestamp())), str(int(AT.timestamp())), "30s")
    ]


async def test_history_raises_metrics_source_unreachable_on_a_client_failure() -> None:
    client = _Client(fails=True)
    source = PrometheusMetricsSource(client=client)  # type: ignore[arg-type]

    with pytest.raises(MetricsSourceUnreachable):
        await source.history(
            matchers=("node_bridge_up",),
            start=datetime(2026, 8, 12, 11, 0, tzinfo=UTC),
            end=AT,
            step_seconds=30,
        )
